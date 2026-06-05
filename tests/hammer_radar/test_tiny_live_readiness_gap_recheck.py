from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.readonly_balance_check import ACCOUNT_NOT_FUNDED
from src.app.hammer_radar.operator.tiny_live_readiness_gap_recheck import (
    CONFIRM_TINY_LIVE_GAP_RECHECK_RECORDING_PHRASE,
    LEDGER_FILENAME,
    NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED,
    STRUCTURALLY_CLOSE_OPERATIONALLY_BLOCKED,
    TINY_LIVE_READINESS_GAP_RECHECK_RECORDED,
    TINY_LIVE_READINESS_GAP_RECHECK_REJECTED,
    build_tiny_live_readiness_gap_recheck,
    load_tiny_live_readiness_gap_recheck_records,
)

NOW = datetime(2026, 6, 5, 22, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
SAFE_ENV = {
    "HAMMER_LIVE_EXECUTION_ENABLED": "false",
    "HAMMER_ALLOW_LIVE_ORDERS": "false",
    "BINANCE_LIVE_TRADING_ENABLED": "false",
    "HAMMER_GLOBAL_KILL_SWITCH": "true",
}


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_strong_evidence(log_dir)
    _write_capture_sync(log_dir, 3)
    _write_funding_sync(log_dir, ACCOUNT_NOT_FUNDED, 0.0)

    payload = build_tiny_live_readiness_gap_recheck(
        log_dir=log_dir,
        config_path=_write_lane_config(tmp_path / "lane_controls.json", mode="paper"),
        risk_contract_config_path=_write_risk_contract(tmp_path / "tiny_live_risk_contracts.json", applied=False),
        env=SAFE_ENV,
        now=NOW,
    )

    assert payload["record_recheck_requested"] is False
    assert payload["recheck_recorded"] is False
    assert payload["recheck_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_tiny_live_readiness_gap_recheck(
        log_dir=tmp_path / "logs",
        config_path=_write_lane_config(tmp_path / "lane_controls.json", mode="paper"),
        risk_contract_config_path=_write_risk_contract(tmp_path / "tiny_live_risk_contracts.json", applied=False),
        record_recheck=True,
        confirm_tiny_live_gap_recheck="wrong",
        env=SAFE_ENV,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_READINESS_GAP_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert load_tiny_live_readiness_gap_recheck_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_recheck_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_lane_config(tmp_path / "lane_controls.json", mode="paper")
    risk_path = _write_risk_contract(tmp_path / "tiny_live_risk_contracts.json", applied=False)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_readiness_gap_recheck(
        log_dir=log_dir,
        config_path=config_path,
        risk_contract_config_path=risk_path,
        record_recheck=True,
        confirm_tiny_live_gap_recheck=CONFIRM_TINY_LIVE_GAP_RECHECK_RECORDING_PHRASE,
        env=SAFE_ENV,
        now=NOW,
    )
    records = load_tiny_live_readiness_gap_recheck_records(log_dir=log_dir, limit=0)

    assert payload["status"] == TINY_LIVE_READINESS_GAP_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_READINESS_GAP_RECHECK"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_risk == risk_path.read_text(encoding="utf-8")


def test_funding_unknown_or_not_funded_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path)

    assert _hard_blocker_names(payload) >= {"funding"}
    assert payload["operational_readiness"]["funding_status"] == ACCOUNT_NOT_FUNDED


def test_fresh_capture_below_threshold_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, capture_count=3)

    assert "fresh_capture_threshold" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["fresh_capture_count"] == 3
    assert payload["operational_readiness"]["capture_threshold_met"] is False


def test_risk_contract_missing_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, risk_applied=False)

    assert "risk_contract" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["risk_contract_applied"] is False


def test_lane_mode_paper_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, lane_mode="paper")

    assert "lane_mode" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["lane_mode"] == "paper"


def test_operator_approval_false_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path)

    assert "operator_approval" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["operator_approval"] is False


def test_live_flags_false_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, env=SAFE_ENV)

    assert "live_flags" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["live_flags_armed"] is False


def test_kill_switch_false_or_unknown_is_hard_blocker(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, env={**SAFE_ENV, "HAMMER_GLOBAL_KILL_SWITCH": "true"})

    assert "kill_switch" in _hard_blocker_names(payload)
    assert payload["operational_readiness"]["kill_switch_allows_live"] is False


def test_evidence_stack_can_be_strong_while_operational_readiness_is_blocked(tmp_path: Path) -> None:
    payload = _build_default_blocked(tmp_path, capture_count=3)

    evidence = payload["evidence_stack_summary"]
    assert evidence["pattern_lane_matrix_found"] is True
    assert evidence["anchor_confluence_found"] is True
    assert evidence["full_spectrum_harvester_found"] is True
    assert evidence["primary_pair_score"] == 84
    assert evidence["secondary_pair_scores"]["bearish_engulfing"] == 82
    assert evidence["summary_level_confluence_available"] is True
    assert payload["tiny_live_distance"]["distance"] == NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED
    assert payload["candidate_context"]["live_authorized"] is False


def test_structurally_close_operationally_blocked_when_funding_and_capture_clear(tmp_path: Path) -> None:
    payload = _build_default_blocked(
        tmp_path,
        funding_status="FUNDED",
        available=50.0,
        capture_count=10,
        risk_applied=True,
        lane_mode="tiny_live",
        env={
            "HAMMER_LIVE_EXECUTION_ENABLED": "true",
            "HAMMER_ALLOW_LIVE_ORDERS": "true",
            "BINANCE_LIVE_TRADING_ENABLED": "true",
            "HAMMER_GLOBAL_KILL_SWITCH": "false",
        },
    )

    assert payload["operational_readiness"]["capture_threshold_met"] is True
    assert payload["tiny_live_distance"]["distance"] == STRUCTURALLY_CLOSE_OPERATIONALLY_BLOCKED
    assert "operator_approval" in _hard_blocker_names(payload)


def test_no_live_authorization_env_config_mutation_or_unsafe_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = _write_lane_config(tmp_path / "lane_controls.json", mode="paper")
    risk_path = _write_risk_contract(tmp_path / "tiny_live_risk_contracts.json", applied=False)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_readiness_gap_recheck(
            log_dir=log_dir,
            config_path=config_path,
            risk_contract_config_path=risk_path,
            env=SAFE_ENV,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_risk == risk_path.read_text(encoding="utf-8")
    assert payload["candidate_context"]["paper_only"] is True
    assert payload["candidate_context"]["live_authorized"] is False
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "live_authorization_created",
        "signal_origin_promoted",
        "lane_promoted",
        "pattern_family_live_authorized",
        "anchor_live_authorized",
        "confluence_live_authorized",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "tiny-live-readiness-gap-recheck",
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
    assert payload["candidate_context"]["primary_lane"] == LANE_8M_SHORT
    assert "tiny-live-readiness-gap-recheck" in help_result.stdout


def _build_default_blocked(
    tmp_path: Path,
    *,
    funding_status: str = ACCOUNT_NOT_FUNDED,
    available: float | None = 0.0,
    capture_count: int = 3,
    risk_applied: bool = False,
    lane_mode: str = "paper",
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    log_dir = tmp_path / "logs"
    _write_strong_evidence(log_dir)
    _write_capture_sync(log_dir, capture_count)
    _write_funding_sync(log_dir, funding_status, available)
    return build_tiny_live_readiness_gap_recheck(
        log_dir=log_dir,
        config_path=_write_lane_config(tmp_path / "lane_controls.json", mode=lane_mode),
        risk_contract_config_path=_write_risk_contract(tmp_path / "tiny_live_risk_contracts.json", applied=risk_applied),
        env=env or SAFE_ENV,
        now=NOW,
    )


def _hard_blocker_names(payload: dict[str, object]) -> set[str]:
    return {
        str(blocker["blocker"])
        for blocker in payload["tiny_live_blockers"]  # type: ignore[index]
        if blocker["severity"] == "HARD"
    }


def _write_strong_evidence(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    _append_json(
        log_dir / "pattern_lane_matrix_review.ndjson",
        {
            "event_type": "PATTERN_LANE_MATRIX_REVIEW",
            "status": "PATTERN_LANE_MATRIX_REVIEW_RECORDED",
            "matrix_id": "r205-test",
            "pattern_lane_pair_matrix": [
                {"lane_key": LANE_8M_SHORT, "signal_origin": "hammer_wick_reversal", "pair_score": 84},
                {"lane_key": LANE_8M_SHORT, "signal_origin": "bearish_engulfing", "pair_score": 82},
                {"lane_key": LANE_8M_SHORT, "signal_origin": "three_black_crows", "pair_score": 68},
            ],
        },
    )
    _append_json(
        log_dir / "anchor_signal_confluence_matrix.ndjson",
        {
            "event_type": "ANCHOR_SIGNAL_CONFLUENCE_MATRIX",
            "status": "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED",
            "matrix_id": "r203-test",
            "input_summary": {"summary_level_matches_found": 594, "event_level_matches_found": 0},
        },
    )
    _append_json(
        log_dir / "full_spectrum_harvester_expansion.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION",
            "status": "FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED",
            "harvest_id": "r198-test",
        },
    )
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "status": "FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED",
            "generated_at": NOW.isoformat(),
        },
    )


def _write_capture_sync(log_dir: Path, count: int) -> None:
    _append_json(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "event_type": "CAPTURE_COUNT_SYNC_8M_SHORT",
            "status": "CAPTURE_COUNT_SYNC_RECORDED",
            "capture_count": {
                "fresh_capture_count": count,
                "required_fresh_capture_count": 10,
                "threshold_met": count >= 10,
                "latest_captured_signal_id": f"fresh-{count}",
            },
            "threshold_status": "CAPTURE_THRESHOLD_MET" if count >= 10 else "CAPTURE_THRESHOLD_NOT_MET",
        },
    )


def _write_funding_sync(log_dir: Path, status: str, available: float | None) -> None:
    _append_json(
        log_dir / "funding_gate_role_specific_sync.ndjson",
        {
            "event_type": "FUNDING_GATE_ROLE_SPECIFIC_SYNC",
            "status": "FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED",
            "latest_balance_state": {
                "balance_readiness": status,
                "available_balance_usdt": available,
                "minimum_balance_required_estimate_usdt": 44.0,
                "funding_ready": status == "FUNDED",
            },
            "account_read_role_state": {
                "role_specific_pair_present": True,
                "legacy_fallback_used": False,
                "future_live_disabled": True,
            },
        },
    )


def _write_lane_config(path: Path, *, mode: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    {
                        "symbol": "BTCUSDT",
                        "timeframe": "8m",
                        "direction": "short",
                        "entry_mode": "ladder_close_50_618",
                        "mode": mode,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _write_risk_contract(path: Path, *, applied: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    contracts = []
    if applied:
        contracts.append(
            {
                "candidate_id": "normal|BTCUSDT|8m|short|ladder_close_50_618",
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "enabled_for_preflight": True,
                "max_margin_usdt": 44.0,
            }
        )
    path.write_text(
        json.dumps({"funding_config": {"max_margin_usdt": 44.0}, "risk_contracts": contracts}, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _append_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
