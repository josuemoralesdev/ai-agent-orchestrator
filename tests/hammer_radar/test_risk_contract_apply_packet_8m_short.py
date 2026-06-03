from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.risk_contract_apply_packet_8m_short import (
    APPLY_PACKET_BLOCKED_BY_EVIDENCE,
    APPLY_PACKET_BLOCKED_BY_FUNDING,
    APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL,
    CONFIRM_RISK_CONTRACT_APPLY_PACKET_RECORDING_PHRASE,
    LEDGER_FILENAME,
    RISK_CONTRACT_APPLY_PACKET_BLOCKED,
    RISK_CONTRACT_APPLY_PACKET_RECORDED,
    RISK_CONTRACT_APPLY_PACKET_REJECTED,
    build_risk_contract_apply_packet_8m_short,
    load_risk_contract_apply_packet_records,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_risk_contract_apply_packet_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["packet_recorded"] is False
    assert payload["packet_id"] is None
    assert payload["record_packet_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_risk_contract_apply_packet_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        record_packet=True,
        confirm_risk_contract_apply_packet="wrong",
        now=NOW,
    )

    assert payload["status"] == RISK_CONTRACT_APPLY_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_risk_contract_apply_packet_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = build_risk_contract_apply_packet_8m_short(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        risk_contract_config_path=risk_path,
        record_packet=True,
        confirm_risk_contract_apply_packet=CONFIRM_RISK_CONTRACT_APPLY_PACKET_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_risk_contract_apply_packet_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == RISK_CONTRACT_APPLY_PACKET_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "RISK_CONTRACT_APPLY_PACKET_8M_SHORT"
    assert before_env == dict(os.environ)
    assert config_path.read_text(encoding="utf-8") == before_config
    assert risk_path.read_text(encoding="utf-8") == before_risk


def test_evidence_below_threshold_blocks_apply_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(3):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_risk_contract_apply_packet_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )

    assert payload["status"] == RISK_CONTRACT_APPLY_PACKET_BLOCKED
    assert payload["evidence_gate"]["fresh_capture_count"] == 3
    assert payload["evidence_gate"]["required_fresh_capture_count"] == 10
    assert payload["evidence_gate"]["threshold_met"] is False
    assert payload["evidence_gate"]["source"] == "R177/R176"
    assert payload["apply_packet_readiness"] == APPLY_PACKET_BLOCKED_BY_EVIDENCE
    assert payload["future_config_patch_preview"]["would_write_config_now"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["lane_config_written"] is False


def test_evidence_ready_but_funding_blocked_blocks(tmp_path: Path) -> None:
    with patch(
        "src.app.hammer_radar.operator.risk_contract_apply_packet_8m_short.build_evidence_threshold_recheck_8m_short",
        return_value=_evidence_recheck(threshold_met=True, funding_ready=False),
    ):
        payload = build_risk_contract_apply_packet_8m_short(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
            now=NOW,
        )

    assert payload["apply_packet_readiness"] == APPLY_PACKET_BLOCKED_BY_FUNDING
    assert payload["funding_gate"]["funding_status"] == "ACCOUNT_NOT_FUNDED"
    assert payload["funding_gate"]["available_balance_usdt"] == 0.0
    assert payload["funding_gate"]["funding_ready"] is False
    assert "funding not ready" in payload["blockers"]


def test_evidence_and_funding_ready_but_operator_missing_blocks(tmp_path: Path) -> None:
    with patch(
        "src.app.hammer_radar.operator.risk_contract_apply_packet_8m_short.build_evidence_threshold_recheck_8m_short",
        return_value=_evidence_recheck(threshold_met=True, funding_ready=True),
    ):
        payload = build_risk_contract_apply_packet_8m_short(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
            now=NOW,
        )

    assert payload["apply_packet_readiness"] == APPLY_PACKET_BLOCKED_BY_OPERATOR_APPROVAL
    assert "operator approval missing" in payload["blockers"]
    assert "config write not authorized" in payload["blockers"]
    assert payload["future_config_patch_preview"]["would_write_config_now"] is False


def test_future_config_patch_preview_is_never_write_now(tmp_path: Path) -> None:
    payload = build_risk_contract_apply_packet_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        now=NOW,
    )
    preview = payload["future_config_patch_preview"]

    assert preview["would_write_config_now"] is False
    assert preview["would_create_target_contract"] is True
    assert preview["would_modify_existing_contract"] is False
    assert preview["preview_only"] is True
    assert preview["patch_preview"]["apply_allowed_now"] is False


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "protective_preview") as protective_preview,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
        patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
        patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
    ):
        payload = build_risk_contract_apply_packet_8m_short(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            risk_contract_config_path=risk_path,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    protective_preview.assert_not_called()
    submit_test_order.assert_not_called()
    submit_protective_test.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    build_signed_test_order_request.assert_not_called()
    build_signed_protective_order_requests.assert_not_called()
    assert before_env == dict(os.environ)
    assert config_path.read_text(encoding="utf-8") == before_config
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["lane_config_written"] is False


def test_no_order_live_transfer_withdraw_or_signed_actions(tmp_path: Path) -> None:
    payload = build_risk_contract_apply_packet_8m_short(
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
    assert safety["binance_order_endpoint_called"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
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
            "risk-contract-apply-packet-8m-short",
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
    assert "risk_contract_draft" in payload
    assert "future_config_patch_preview" in payload
    assert "risk-contract-apply-packet-8m-short" in help_result.stdout


def _evidence_recheck(*, threshold_met: bool, funding_ready: bool) -> dict[str, object]:
    return {
        "status": "EVIDENCE_THRESHOLD_RECHECK_BLOCKED",
        "readiness": "EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED",
        "recheck_recorded": False,
        "capture_threshold_state": {
            "fresh_capture_count": 10 if threshold_met else 3,
            "required_fresh_capture_count": 10,
            "threshold_met": threshold_met,
            "latest_captured_signal_id": "fresh-short-9" if threshold_met else "fresh-short-2",
        },
        "funding_context": {
            "funding_status": "ACCOUNT_FUNDED_READY_FOR_REVIEW" if funding_ready else "ACCOUNT_NOT_FUNDED",
            "available_balance_usdt": 100.0 if funding_ready else 0.0,
            "funding_ready": funding_ready,
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
