from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short import (
    CONFIRM_EVIDENCE_THRESHOLD_RECHECK_RECORDING_PHRASE,
    EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED,
    EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED,
    EVIDENCE_THRESHOLD_NOT_MET,
    EVIDENCE_THRESHOLD_RECHECK_RECORDED,
    EVIDENCE_THRESHOLD_RECHECK_REJECTED,
    FUND_ACCOUNT_LATER,
    KEEP_WATCHER_RUNNING,
    LEDGER_FILENAME,
    RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY,
    START_WATCHER_NOW,
    build_evidence_threshold_recheck_8m_short,
    classify_evidence_threshold_readiness,
    load_evidence_threshold_recheck_records,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["recheck_recorded"] is False
    assert payload["record_recheck_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_recheck=True,
        confirm_evidence_threshold_recheck="wrong",
        now=NOW,
    )

    assert payload["status"] == EVIDENCE_THRESHOLD_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert load_evidence_threshold_recheck_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=config_path,
        risk_contract_config_path=risk_path,
        record_recheck=True,
        confirm_evidence_threshold_recheck=CONFIRM_EVIDENCE_THRESHOLD_RECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_evidence_threshold_recheck_records(log_dir=log_dir, limit=0)

    assert payload["status"] == EVIDENCE_THRESHOLD_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "EVIDENCE_THRESHOLD_RECHECK_8M_SHORT"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_risk == risk_path.read_text(encoding="utf-8")


def test_below_10_captures_threshold_not_met(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(3):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["capture_threshold_state"]["fresh_capture_count"] == 3
    assert payload["capture_threshold_state"]["required_fresh_capture_count"] == 10
    assert payload["capture_threshold_state"]["threshold_met"] is False
    assert payload["readiness"] == EVIDENCE_THRESHOLD_NOT_MET


def test_10_captures_and_funding_blocked_classifies_funding_blocked(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(10):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    with (
        patch(
            "src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short.build_short_evidence_recheck_packet",
            return_value=_short_evidence_packet_ready(),
        ),
        patch(
            "src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short.build_funding_gate_role_specific_sync",
            return_value=_funding_sync(funding_ready=False, status="ACCOUNT_NOT_FUNDED", available=0.0),
        ),
    ):
        payload = build_evidence_threshold_recheck_8m_short(
            log_dir=log_dir,
            config_path=_write_config(tmp_path / "lane_controls.json"),
            risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
            now=NOW,
        )

    assert payload["readiness"] == EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED
    assert payload["funding_context"]["funding_status"] == "ACCOUNT_NOT_FUNDED"
    assert payload["funding_context"]["available_balance_usdt"] == 0.0
    assert payload["recommended_next_operator_move"] == FUND_ACCOUNT_LATER


def test_10_captures_funding_ready_and_risk_contract_blocked(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(10):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    with (
        patch(
            "src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short.build_short_evidence_recheck_packet",
            return_value=_short_evidence_packet_ready(),
        ),
        patch(
            "src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short.build_funding_gate_role_specific_sync",
            return_value=_funding_sync(funding_ready=True, status="ACCOUNT_FUNDED_READY_FOR_REVIEW", available=100.0),
        ),
        patch(
            "src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short.build_short_risk_contract_apply_review",
            return_value=_risk_review(target_contract_exists=False, applied=False),
        ),
    ):
        payload = build_evidence_threshold_recheck_8m_short(
            log_dir=log_dir,
            config_path=_write_config(tmp_path / "lane_controls.json"),
            risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
            now=NOW,
        )

    assert payload["readiness"] == EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED
    assert payload["risk_contract_context"]["target_contract_exists"] is False
    assert payload["risk_contract_context"]["risk_contract_applied"] is False
    assert payload["recommended_next_operator_move"] == RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY


def test_watcher_stale_recommends_start_watcher_now(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=600))

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["capture_threshold_state"]["watcher_stale"] is True
    assert payload["recommended_next_operator_move"] == START_WATCHER_NOW


def test_watcher_running_below_threshold_recommends_keep_running(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["capture_threshold_state"]["watcher_likely_running"] is True
    assert payload["recommended_next_operator_move"] == KEEP_WATCHER_RUNNING


def test_classify_funding_before_risk_contract() -> None:
    readiness = classify_evidence_threshold_readiness(
        capture_threshold_state={"threshold_met": True},
        short_evidence_state={"evidence_ready_for_review": True},
        funding_context={"funding_ready": False},
        risk_contract_context={"risk_contract_applied": False},
    )

    assert readiness == EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))
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
        payload = build_evidence_threshold_recheck_8m_short(
            log_dir=log_dir,
            config_path=config_path,
            risk_contract_config_path=risk_path,
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
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["lane_config_written"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_no_order_live_transfer_withdraw_or_signed_actions(tmp_path: Path) -> None:
    payload = build_evidence_threshold_recheck_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    safety = payload["safety"]

    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["executable_payload_created"] is False
    assert safety["signed_order_request_created"] is False
    assert safety["signed_trading_request_created"] is False
    assert safety["signed_readonly_request_created"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["secrets_shown"] is False
    assert safety["global_live_flags_changed"] is False
    assert safety["kill_switch_disabled"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "evidence-threshold-recheck-8m-short",
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
    assert "evidence-threshold-recheck-8m-short" in help_result.stdout


def _short_evidence_packet_ready() -> dict[str, object]:
    return {
        "status": "SHORT_EVIDENCE_RECHECK_READY",
        "historical_evidence": {
            "paper_outcome_count": 30,
            "win_rate_pct": 60.0,
            "avg_pnl_pct": 0.08,
        },
        "promotion_readiness": {
            "readiness": "PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW",
            "ready_for_operator_review": True,
        },
    }


def _funding_sync(*, funding_ready: bool, status: str, available: float) -> dict[str, object]:
    return {
        "status": "FUNDING_GATE_ROLE_SPECIFIC_SYNC_READY" if funding_ready else "FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED",
        "latest_balance_state": {
            "record_found": True,
            "balance_readiness": status,
            "available_balance_usdt": available,
            "funding_ready": funding_ready,
        },
        "funding_gate": {
            "funding_sync_status": "FUNDING_SYNC_READY_FOR_REVIEW" if funding_ready else "FUNDING_SYNC_ACCOUNT_NOT_FUNDED",
            "funding_ready": funding_ready,
        },
    }


def _risk_review(*, target_contract_exists: bool, applied: bool) -> dict[str, object]:
    return {
        "status": "SHORT_RISK_CONTRACT_APPLY_REVIEW_BLOCKED",
        "readiness": "APPLY_REVIEW_BLOCKED_BY_OPERATOR_APPROVAL",
        "existing_contract_state": {
            "target_contract_exists": target_contract_exists,
            "target_contract_enabled_for_preflight": applied,
        },
    }


def _write_capture(log_dir: Path, signal_id: str) -> None:
    _append(
        log_dir / "short_paper_evidence_capture.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
            "status": "SHORT_PAPER_EVIDENCE_CAPTURED",
            "capture_id": f"capture-{signal_id}",
            "captured_signal_id": signal_id,
            "captured_lane_key": LANE_8M_SHORT,
            "paper_evidence_captured": True,
            "target_lane": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _write_heartbeat(log_dir: Path, generated_at: datetime) -> None:
    _append(
        log_dir / "short_paper_evidence_capture_heartbeats.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT",
            "capture_id": "capture-watch",
            "generated_at": generated_at.isoformat(),
            "iteration": 4,
            "sleep_seconds": 60,
            "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
            "target_lane": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _write_config(path: Path) -> Path:
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
                        "mode": "paper",
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _write_risk_contract_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"risk_contracts": []}, sort_keys=True), encoding="utf-8")
    return path


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
