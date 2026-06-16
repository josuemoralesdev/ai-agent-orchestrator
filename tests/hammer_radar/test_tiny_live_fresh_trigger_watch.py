from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    FRESH_TRIGGER_BLOCKED,
    FRESH_TRIGGER_NOT_CHECKED,
    FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW,
    FRESH_TRIGGER_WAIT,
    build_tiny_live_fresh_trigger_watch,
)
from tests.hammer_radar.test_tiny_live_one_shot_pre_activation_gate import (
    LANE_44M_LONG,
    LANE_44M_SHORT,
    NOW,
    _binance_ready,
    _contract,
    _post_manual_verified,
    _watch_wait,
    _watch_with_candidate,
    _write_risk_contracts,
)


def test_no_candidate_pre_activation_ready_waits(tmp_path: Path) -> None:
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        now=NOW,
    )

    assert payload["status"] == FRESH_TRIGGER_WAIT
    assert payload["pre_activation_ready_to_wait"] is True
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["next_required_step"] == "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
    assert payload["alert_should_send"] is False
    _assert_no_submit(payload)


def test_fresh_paper_only_candidate_blocks_and_recommends_paper_review(tmp_path: Path) -> None:
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(live_class="PAPER_ONLY", status="BLOCKED_PAPER_ONLY"),
        now=NOW,
    )

    assert payload["status"] == FRESH_TRIGGER_BLOCKED
    assert "paper_only" in payload["blockers"]
    assert payload["recommended_operator_move"] == "STRATEGY_LAB_PAPER_REVIEW"
    _assert_no_submit(payload)


def test_fresh_near_miss_candidate_blocks_and_no_submit(tmp_path: Path) -> None:
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(
            live_class="NEAR_MISS_INCUBATOR",
            status="BLOCKED_NEAR_MISS",
        ),
        now=NOW,
    )

    assert payload["status"] == FRESH_TRIGGER_BLOCKED
    assert "near_miss" in payload["blockers"]
    assert payload["submit_allowed"] is False


def test_fresh_approved_live_qualified_candidate_ready_for_operator_review(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_SHORT)])
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_SHORT, direction="short"),
        now=NOW,
    )

    assert payload["status"] == FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW
    assert payload["approved_lane_match"] is True
    assert payload["exact_lane_risk_contract_valid"] is True
    assert payload["protective_triplet_preview_valid"] is True
    assert payload["next_required_step"] == "RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW"
    assert payload["alert_should_send"] is False
    assert payload["telegram_compatible_payload"]["send_enabled"] is False
    _assert_no_submit(payload)


def test_send_telegram_default_false_and_explicit_send_does_not_send_network(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        now=NOW,
    )
    explicit = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        send_telegram=True,
        now=NOW,
    )

    assert payload["alert_should_send"] is False
    assert payload["telegram_send_result"]["send_requested"] is False
    assert payload["telegram_send_result"]["sent"] is False
    assert explicit["alert_should_send"] is True
    assert explicit["telegram_send_result"]["sent"] is False
    assert explicit["telegram_send_result"]["status"] == "send_not_implemented_by_r286"


def test_pre_activation_blocked_blocks_trigger_watch(tmp_path: Path) -> None:
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        pre_activation_packet={
            "status": "ONE_SHOT_PRE_ACTIVATION_BLOCKED",
            "blockers": ["wallet_not_ready"],
            "binance_readiness_ready": False,
            "wallet_ready": False,
            "leverage_margin_ready": False,
            "no_conflicting_position": False,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
        },
        now=NOW,
    )

    assert payload["status"] == FRESH_TRIGGER_BLOCKED
    assert "pre_activation_not_ready" in payload["blockers"]
    _assert_no_submit(payload)


def test_telegram_payload_contains_no_secret_signature_or_signed_url(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        now=NOW,
    )

    rendered = json.dumps(payload["telegram_compatible_payload"]).lower()
    assert "api_key" not in rendered
    assert "api secret" not in rendered
    assert "telegram_bot_token" not in rendered
    assert "signature=" not in rendered
    assert "signed_url" not in rendered


def test_records_trigger_watch_to_ndjson(tmp_path: Path) -> None:
    payload = build_tiny_live_fresh_trigger_watch(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        record_trigger_watch=True,
        now=NOW,
    )

    assert payload["trigger_watch_recorded"] is True
    assert (tmp_path / "tiny_live_fresh_trigger_watch.ndjson").exists()
    _assert_no_submit(payload)


def test_api_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/fresh-trigger-watch")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "TINY_LIVE_FRESH_LIVE_QUALIFIED_TRIGGER_WATCH"
    assert payload["status"] == FRESH_TRIGGER_NOT_CHECKED
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_final_console_includes_fresh_trigger_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["fresh_trigger_watch_panel"]

    assert panel["status"] in {
        FRESH_TRIGGER_NOT_CHECKED,
        FRESH_TRIGGER_BLOCKED,
        FRESH_TRIGGER_WAIT,
        FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW,
    }
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_cli_supports_fresh_trigger_watch_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-fresh-trigger-watch",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--load-discovered-binance-readonly-env" in result.stdout
    assert "--fetch-binance-readonly-precision-mark-price" in result.stdout
    assert "--fetch-binance-readonly-account-position" in result.stdout
    assert "--record-trigger-watch" in result.stdout
    assert "--send-telegram" in result.stdout


def _assert_no_submit(payload: dict) -> None:
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    safety = payload["safety"]
    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["binance_order_endpoint_called"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["leverage_change_called"] is False
    assert safety["margin_change_called"] is False
    assert safety["mutation_performed"] is False
    assert safety["secrets_shown"] is False
