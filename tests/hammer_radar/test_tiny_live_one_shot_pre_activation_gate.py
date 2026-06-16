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
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    ONE_SHOT_PRE_ACTIVATION_BLOCKED,
    ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED,
    ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
    ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
    build_tiny_live_one_shot_pre_activation_gate,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    build_explicit_lane_risk_contract,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_55M_LONG = "BTCUSDT|55m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_all_binance_readiness_green_and_no_fresh_candidate_waits_for_trigger(tmp_path: Path) -> None:
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_wait(),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER
    assert payload["next_required_step"] == "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
    assert payload["current_fresh_candidate_exists"] is False
    assert payload["live_qualified_lanes_available"] is True
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_fresh_paper_only_candidate_blocks(tmp_path: Path) -> None:
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(live_class="PAPER_ONLY", status="BLOCKED_PAPER_ONLY"),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_BLOCKED
    assert "strategy_not_live_qualified" in payload["blockers"]
    assert "paper_only" in payload["blockers"]
    assert payload["one_shot_live_allowed"] is False


def test_fresh_near_miss_candidate_blocks(tmp_path: Path) -> None:
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(live_class="NEAR_MISS_INCUBATOR", status="BLOCKED_NEAR_MISS"),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_BLOCKED
    assert "strategy_not_live_qualified" in payload["blockers"]
    assert "near_miss" in payload["blockers"]
    assert payload["submit_allowed"] is False


def test_fresh_approved_live_qualified_candidate_missing_contract_blocks(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[])
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_LONG),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_BLOCKED
    assert payload["approved_lane_match"] is True
    assert payload["exact_lane_risk_contract_found"] is False
    assert "exact_lane_risk_contract_missing" in payload["blockers"]


def test_valid_contract_but_missing_protective_preview_blocks_without_submit(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    watch = _watch_with_candidate(lane_key=LANE_44M_LONG)
    watch["candidate_alert_packet"]["current_candidate"].pop("stop")

    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=watch,
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_BLOCKED
    assert payload["protective_triplet_preview_available"] is False
    assert payload["protective_triplet_preview_valid"] is False
    assert "protective_triplet_preview_missing" in payload["blockers"]
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False


def test_all_gates_green_ready_for_dry_run_trigger_with_no_final_command(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_SHORT)])
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_SHORT, direction="short"),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER
    assert payload["next_required_step"] == "RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW"
    assert payload["protective_triplet_preview_available"] is True
    assert payload["protective_triplet_preview_valid"] is True
    assert payload["one_shot_live_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_no_order_test_order_leverage_margin_mutation_or_secret_flags(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_55M_LONG)])
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_55M_LONG),
        now=NOW,
    )

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
    assert safety["signature_shown"] is False
    assert safety["signed_url_shown"] is False
    rendered = json.dumps(payload)
    assert "signature=" not in rendered


def test_exact_lane_only_no_cross_lane_borrowing(tmp_path: Path) -> None:
    risk_path = _write_risk_contracts(tmp_path, contracts=[_contract(LANE_44M_LONG)])
    payload = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=tmp_path,
        risk_contract_config_path=risk_path,
        binance_readiness=_binance_ready(),
        post_manual_verification=_post_manual_verified(),
        candidate_watch=_watch_with_candidate(lane_key=LANE_44M_SHORT, direction="short"),
        now=NOW,
    )

    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_BLOCKED
    assert payload["current_candidate_lane_key"] == LANE_44M_SHORT
    assert payload["exact_lane_risk_contract_found"] is False
    assert payload["exact_lane_risk_contract"]["no_cross_lane_borrowing"] is True
    assert "exact_lane_risk_contract_missing" in payload["blockers"]


def test_final_console_includes_one_shot_pre_activation_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["one_shot_pre_activation_gate_panel"]

    assert panel["status"] in {
        ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED,
        ONE_SHOT_PRE_ACTIVATION_BLOCKED,
        ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
    }
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


def test_api_endpoint_default_safe_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/one-shot-pre-activation-gate")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_type"] == "TINY_LIVE_ONE_SHOT_PRE_ACTIVATION_GATE"
    assert payload["status"] == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_cli_supports_r285_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-one-shot-pre-activation-gate",
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
    assert "--record-pre-activation-review" in result.stdout


def _binance_ready() -> dict:
    return {
        "status": "BINANCE_READINESS_READY",
        "cap_clears_exchange_minimum": True,
        "wallet_supports_minimum_tiny": True,
        "wallet_supports_configured_margin_budget": True,
        "open_position_conflict": False,
        "current_leverage": 10.0,
        "current_margin_mode": "isolated",
        "leverage_margin_ready": True,
        "autonomous_one_shot_readiness_matrix": {
            "binance_readiness_ready": True,
            "exchange_minimum_ready": True,
            "wallet_ready": True,
            "no_conflicting_position": True,
        },
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "leverage_change_called": False,
            "margin_change_called": False,
            "mutation_performed": False,
            "secrets_shown": False,
        },
    }


def _post_manual_verified() -> dict:
    return {
        "status": "POST_MANUAL_LEVERAGE_MARGIN_VERIFIED",
        "post_manual_alignment_verified": True,
        "leverage_margin_ready": True,
        "wallet_supports_configured_margin_budget": True,
        "open_position_conflict": False,
        "current_leverage": 10.0,
        "current_margin_mode": "isolated",
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "leverage_change_called": False,
            "margin_change_called": False,
            "mutation_performed": False,
            "secrets_shown": False,
        },
    }


def _watch_wait() -> dict:
    return {
        "event_type": "LIVE_QUALIFIED_FRESH_CANDIDATE_WATCH",
        "live_qualified_lanes": [{"strategy_key": LANE_44M_LONG}],
        "near_miss_incubator_lanes": [],
        "paper_only_lanes": [],
        "current_fresh_candidate_status": {
            "qualified_fresh_candidate_exists": False,
            "current_candidate_lane_key": None,
        },
        "candidate_alert_packet": {
            "status": "WAIT",
            "current_candidate": None,
            "strategy_evidence": None,
            "blocked_by": ["no_current_fresh_candidate"],
        },
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
    }


def _watch_with_candidate(
    *,
    lane_key: str = LANE_44M_LONG,
    direction: str = "long",
    live_class: str = "LIVE_QUALIFIED",
    status: str = "LIVE_QUALIFIED_FRESH_CANDIDATE_FOUND",
) -> dict:
    candidate = {
        "signal_id": f"sig-{lane_key.replace('|', '-')}",
        "symbol": "BTCUSDT",
        "timeframe": lane_key.split("|")[1],
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "lane_key": lane_key,
        "age_minutes": 3.0,
        "freshness_status": "fresh",
        "entry": 70000.0,
        "stop": 69300.0 if direction == "long" else 70700.0,
        "take_profit": 71400.0 if direction == "long" else 68600.0,
    }
    return {
        "event_type": "LIVE_QUALIFIED_FRESH_CANDIDATE_WATCH",
        "live_qualified_lanes": [{"strategy_key": LANE_44M_LONG}, {"strategy_key": LANE_44M_SHORT}],
        "near_miss_incubator_lanes": [],
        "paper_only_lanes": [],
        "current_fresh_candidate_status": {
            "qualified_fresh_candidate_exists": live_class == "LIVE_QUALIFIED",
            "current_candidate_lane_key": lane_key,
        },
        "candidate_alert_packet": {
            "status": status,
            "current_candidate": candidate,
            "strategy_evidence": {
                "live_qualification_class": live_class,
                "watch_category": live_class,
                "win_rate_pct": 60.0 if live_class == "LIVE_QUALIFIED" else 47.0,
                "sample_count": 40,
                "avg_pnl_pct": 0.12 if live_class != "PAPER_ONLY" else -0.01,
            },
            "blocked_by": [] if live_class == "LIVE_QUALIFIED" else ["strategy_not_live_qualified"],
        },
        "safety": {"order_placed": False, "real_order_placed": False, "secrets_shown": False},
    }


def _contract(lane_key: str) -> dict:
    return build_explicit_lane_risk_contract(
        lane_key=lane_key,
        strategy_qualification={
            "lane_key": lane_key,
            "win_rate_pct": 60.0,
            "sample_count": 40,
            "avg_pnl_pct": 0.12,
            "min_sample": 30,
            "min_win_rate_pct": 55.0,
            "qualification_status": "QUALIFIED",
        },
        now=NOW,
    )


def _write_risk_contracts(tmp_path: Path, *, contracts: list[dict]) -> Path:
    path = tmp_path / "tiny_live_risk_contracts.json"
    path.write_text(json.dumps({"risk_contracts": contracts}), encoding="utf-8")
    return path
