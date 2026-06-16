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
    CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
    build_tiny_live_binance_autonomous_readiness_binding,
)
from src.app.hammer_radar.operator.tiny_live_leverage_margin_readiness import (
    EXACT_MATCH,
    LEVERAGE_MARGIN_BLOCKED,
    LEVERAGE_MARGIN_NOT_CHECKED,
    LEVERAGE_MARGIN_READY,
    LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW,
    NONZERO_POSITION_MISMATCH,
    POST_MANUAL_EVENT_TYPE,
    POST_MANUAL_LEVERAGE_MARGIN_NOT_CHECKED,
    POST_MANUAL_LEVERAGE_MARGIN_STILL_MISMATCHED,
    POST_MANUAL_LEVERAGE_MARGIN_VERIFIED,
    UNKNOWN_FIELDS,
    ZERO_POSITION_METADATA_MISMATCH,
    build_post_manual_leverage_margin_alignment_verification,
    build_tiny_live_leverage_margin_readiness,
)
from tests.hammer_radar.test_binance_account_position_readonly import _PrivateFakeUrlOpen, _safe_env

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def test_exact_match_is_ready() -> None:
    payload = build_tiny_live_leverage_margin_readiness(
        account_position_snapshot=_snapshot(current_leverage=10, current_margin_mode="isolated"),
        now=NOW,
    )

    assert payload["status"] == LEVERAGE_MARGIN_READY
    assert payload["mismatch_classification"] == EXACT_MATCH
    assert payload["current_leverage"] == 10.0
    assert payload["current_margin_mode"] == "isolated"
    assert payload["zero_position"] is True
    assert payload["live_submit_blocked_by_leverage_margin"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_post_manual_exact_match_is_verified_and_ready() -> None:
    payload = build_post_manual_leverage_margin_alignment_verification(
        account_position_snapshot=_snapshot(current_leverage=10, current_margin_mode="isolated"),
        now=NOW,
    )

    assert payload["event_type"] == POST_MANUAL_EVENT_TYPE
    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_VERIFIED
    assert payload["operator_reported_manual_adjustment"] is True
    assert payload["expected_leverage"] == 10.0
    assert payload["expected_margin_mode"] == "isolated"
    assert payload["current_leverage"] == 10.0
    assert payload["current_margin_mode"] == "isolated"
    assert payload["post_manual_alignment_verified"] is True
    assert payload["leverage_margin_ready"] is True
    assert payload["leverage_margin_blocks_one_shot"] is False
    assert payload["zero_position"] is True
    assert payload["open_position_conflict"] is False
    assert payload["wallet_supports_configured_margin_budget"] is True
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["safety"]["mutation_performed"] is False


def test_zero_position_mismatch_requires_manual_review_not_ready() -> None:
    payload = build_tiny_live_leverage_margin_readiness(
        account_position_snapshot=_snapshot(current_leverage=20, current_margin_mode="cross"),
        now=NOW,
    )

    assert payload["status"] == LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW
    assert payload["mismatch_classification"] == ZERO_POSITION_METADATA_MISMATCH
    assert payload["zero_position"] is True
    assert payload["manual_only_adjustment_required"] is True
    assert payload["mutation_required"] is True
    assert payload["mutation_performed"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["live_submit_blocked_by_leverage_margin"] is True
    assert payload["final_command_available"] is False


def test_post_manual_mismatch_remains_blocked_for_manual_recheck() -> None:
    payload = build_post_manual_leverage_margin_alignment_verification(
        account_position_snapshot=_snapshot(current_leverage=20, current_margin_mode="cross"),
        now=NOW,
    )

    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_STILL_MISMATCHED
    assert payload["post_manual_alignment_verified"] is False
    assert payload["leverage_margin_ready"] is False
    assert payload["leverage_margin_blocks_one_shot"] is True
    assert "manual_binance_ui_recheck_required" in payload["readiness_blockers"]
    assert payload["final_command_available"] is False


def test_nonzero_position_mismatch_blocks() -> None:
    payload = build_tiny_live_leverage_margin_readiness(
        account_position_snapshot=_snapshot(
            current_leverage=20,
            current_margin_mode="cross",
            position_amt="-0.001",
            notional="-40",
            open_position_conflict=True,
        ),
        now=NOW,
    )

    assert payload["status"] == LEVERAGE_MARGIN_BLOCKED
    assert payload["mismatch_classification"] == NONZERO_POSITION_MISMATCH
    assert payload["zero_position"] is False
    assert payload["live_submit_blocked_by_leverage_margin"] is True


def test_post_manual_nonzero_position_still_blocks() -> None:
    payload = build_post_manual_leverage_margin_alignment_verification(
        account_position_snapshot=_snapshot(
            current_leverage=10,
            current_margin_mode="isolated",
            position_amt="-0.001",
            notional="-40",
            open_position_conflict=True,
        ),
        now=NOW,
    )

    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_STILL_MISMATCHED
    assert payload["zero_position"] is False
    assert payload["open_position_conflict"] is True
    assert payload["leverage_margin_ready"] is False
    assert payload["leverage_margin_blocks_one_shot"] is True
    assert payload["final_command_available"] is False


def test_unknown_fields_block_or_require_review_but_never_ready() -> None:
    payload = build_tiny_live_leverage_margin_readiness(
        account_position_snapshot=_snapshot(current_leverage=None, current_margin_mode=None),
        now=NOW,
    )

    assert payload["status"] == LEVERAGE_MARGIN_BLOCKED
    assert payload["mismatch_classification"] == UNKNOWN_FIELDS
    assert payload["manual_only_adjustment_required"] is True
    assert payload["mutation_required"] is True
    assert payload["final_command_available"] is False


def test_not_checked_default_is_no_network_and_no_final_command() -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_leverage_margin_readiness(now=NOW)

    urlopen.assert_not_called()
    assert payload["status"] == LEVERAGE_MARGIN_NOT_CHECKED
    assert payload["safety"]["network_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False


def test_post_manual_default_is_not_checked_no_network_and_no_final_command() -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_post_manual_leverage_margin_alignment_verification(now=NOW)

    urlopen.assert_not_called()
    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_NOT_CHECKED
    assert payload["post_manual_leverage_margin_verification_panel"]["status"] == (
        POST_MANUAL_LEVERAGE_MARGIN_NOT_CHECKED
    )
    assert payload["safety"]["network_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False


def test_readonly_fetch_calls_no_order_or_mutation_endpoints() -> None:
    fake = _PrivateFakeUrlOpen(available_balance="20", wallet_balance="20", position_amt="0", notional="0")
    payload = build_tiny_live_leverage_margin_readiness(
        fetch_binance_readonly_account_position=True,
        confirm_binance_readonly_account_position=CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
        env=_safe_env(),
        now=NOW,
        urlopen_func=fake,
    )

    urls = [call.full_url for call in fake.calls]
    assert len(urls) == 2
    assert all("/fapi/v1/order" not in url for url in urls)
    assert all("/fapi/v1/leverage" not in url for url in urls)
    assert all("/fapi/v1/marginType" not in url for url in urls)
    assert payload["status"] == LEVERAGE_MARGIN_READY
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["leverage_change_called"] is False
    assert payload["safety"]["margin_change_called"] is False
    assert payload["safety"]["signed_trading_request_created"] is False
    assert payload["safety"]["signed_order_request_created"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_post_manual_readonly_fetch_calls_no_order_or_mutation_endpoints() -> None:
    fake = _PrivateFakeUrlOpen(available_balance="20", wallet_balance="20", position_amt="0", notional="0")
    payload = build_post_manual_leverage_margin_alignment_verification(
        fetch_binance_readonly_account_position=True,
        confirm_binance_readonly_account_position=CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
        env=_safe_env(),
        now=NOW,
        urlopen_func=fake,
    )

    urls = [call.full_url for call in fake.calls]
    assert len(urls) == 2
    assert all("/fapi/v1/order" not in url for url in urls)
    assert all("/fapi/v1/leverage" not in url for url in urls)
    assert all("/fapi/v1/marginType" not in url for url in urls)
    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_VERIFIED
    assert payload["current_leverage"] == 10.0
    assert payload["current_margin_mode"] == "isolated"
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["leverage_change_called"] is False
    assert payload["safety"]["margin_change_called"] is False
    assert payload["safety"]["mutation_performed"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_no_secrets_printed() -> None:
    payload = build_tiny_live_leverage_margin_readiness(
        fetch_binance_readonly_account_position=True,
        confirm_binance_readonly_account_position=CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
        env=_safe_env(),
        now=NOW,
        urlopen_func=_PrivateFakeUrlOpen(available_balance="20", wallet_balance="20", position_amt="0", notional="0"),
    )
    rendered = json.dumps(payload)

    assert "account-read-key" not in rendered
    assert "account-read-secret" not in rendered
    assert "signature=" not in rendered
    assert payload["safety"]["secrets_shown"] is False


def test_post_manual_no_secrets_or_signatures_printed() -> None:
    payload = build_post_manual_leverage_margin_alignment_verification(
        fetch_binance_readonly_account_position=True,
        confirm_binance_readonly_account_position=CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
        env=_safe_env(),
        now=NOW,
        urlopen_func=_PrivateFakeUrlOpen(available_balance="20", wallet_balance="20", position_amt="0", notional="0"),
    )
    rendered = json.dumps(payload)

    assert "account-read-key" not in rendered
    assert "account-read-secret" not in rendered
    assert "signature=" not in rendered
    assert payload["safety"]["signature_shown"] is False
    assert payload["safety"]["signed_url_shown"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_autonomous_matrix_includes_leverage_margin_readiness(tmp_path: Path) -> None:
    payload = build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=tmp_path,
        account_position_snapshot=_snapshot(current_leverage=20, current_margin_mode="cross"),
        now=NOW,
    )

    matrix = payload["autonomous_one_shot_readiness_matrix"]
    assert payload["leverage_margin_status"] == LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW
    assert payload["leverage_margin_ready"] is False
    assert payload["leverage_margin_blocks_one_shot"] is True
    assert matrix["leverage_margin_ready"] is False
    assert matrix["leverage_margin_blocks_one_shot"] is True
    assert matrix["one_shot_live_allowed"] is False
    assert payload["final_command_available"] is False


def test_autonomous_matrix_keeps_one_shot_blocked_when_post_manual_verified(tmp_path: Path) -> None:
    payload = build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=tmp_path,
        account_position_snapshot=_snapshot(current_leverage=10, current_margin_mode="isolated"),
        now=NOW,
    )

    matrix = payload["autonomous_one_shot_readiness_matrix"]
    assert payload["post_manual_leverage_margin_verification"]["status"] == (
        POST_MANUAL_LEVERAGE_MARGIN_VERIFIED
    )
    assert payload["leverage_margin_ready"] is True
    assert payload["leverage_margin_blocks_one_shot"] is False
    assert matrix["leverage_margin_ready"] is True
    assert matrix["leverage_margin_blocks_one_shot"] is False
    assert matrix["one_shot_live_allowed"] is False
    assert payload["final_command_available"] is False


def test_final_console_includes_leverage_margin_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["leverage_margin_readiness_panel"]

    assert panel["status"] == LEVERAGE_MARGIN_NOT_CHECKED
    assert panel["mutation_performed"] is False
    assert panel["safe_next_cli_command"]
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_final_console_includes_post_manual_verification_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    build_post_manual_leverage_margin_alignment_verification(
        log_dir=tmp_path,
        account_position_snapshot=_snapshot(current_leverage=10, current_margin_mode="isolated"),
        now=NOW,
    )

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["post_manual_leverage_margin_verification_panel"]

    assert panel["status"] == POST_MANUAL_LEVERAGE_MARGIN_VERIFIED
    assert panel["current_leverage"] == 10.0
    assert panel["current_margin_mode"] == "isolated"
    assert panel["post_manual_alignment_verified"] is True
    assert panel["leverage_margin_ready"] is True
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_supports_loader_and_confirmation_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-leverage-margin-readiness",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--load-discovered-binance-readonly-env" in result.stdout
    assert "--fetch-binance-readonly-account-position" in result.stdout
    assert "--confirm-binance-readonly-account-position" in result.stdout


def test_post_manual_cli_supports_loader_and_confirmation_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-post-manual-leverage-margin-verification",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--load-discovered-binance-readonly-env" in result.stdout
    assert "--fetch-binance-readonly-account-position" in result.stdout
    assert "--confirm-binance-readonly-account-position" in result.stdout


def test_api_endpoint_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/leverage-margin-readiness")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "TINY_LIVE_LEVERAGE_MARGIN_READINESS"
    assert payload["status"] == LEVERAGE_MARGIN_NOT_CHECKED
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["safety"]["network_allowed"] is False


def test_post_manual_api_endpoint_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/post-manual-leverage-margin-verification")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == POST_MANUAL_EVENT_TYPE
    assert payload["status"] == POST_MANUAL_LEVERAGE_MARGIN_NOT_CHECKED
    assert payload["post_manual_leverage_margin_verification_panel"]["status"] == (
        POST_MANUAL_LEVERAGE_MARGIN_NOT_CHECKED
    )
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["safety"]["network_allowed"] is False


def _snapshot(
    *,
    current_leverage: float | None,
    current_margin_mode: str | None,
    position_amt: str | float = "0",
    notional: str | float = "0",
    open_position_conflict: bool = False,
) -> dict:
    leverage_matches = current_leverage == 10
    margin_matches = current_margin_mode == "isolated"
    return {
        "account_position_readiness_status": "READY",
        "account_balance_checked": True,
        "position_risk_checked": True,
        "leverage_checked": current_leverage is not None,
        "margin_mode_checked": current_margin_mode is not None,
        "wallet_supports_minimum_tiny": True,
        "wallet_supports_configured_margin_budget": True,
        "open_position_conflict": open_position_conflict,
        "btcusdt_position_amt": position_amt,
        "btcusdt_position_side": "BOTH",
        "btcusdt_position_notional": notional,
        "current_leverage": current_leverage,
        "current_margin_mode": current_margin_mode,
        "leverage_matches_expectation": leverage_matches,
        "margin_mode_matches_expectation": margin_matches,
        "readiness_blockers": [],
        "safety": {
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "leverage_change_called": False,
            "margin_change_called": False,
            "signed_trading_request_created": False,
            "signed_order_request_created": False,
            "secrets_shown": False,
        },
    }
