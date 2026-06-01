from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    CONFIRM_SHORT_EVIDENCE_RECHECK_RECORDING_PHRASE,
    DO_NOT_PROMOTE,
    LEDGER_FILENAME,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    SHORT_EVIDENCE_RECHECK_READY,
    SHORT_EVIDENCE_RECHECK_RECORDED,
    SHORT_EVIDENCE_RECHECK_REJECTED,
    build_short_evidence_recheck_packet,
    classify_short_promotion_readiness,
    load_short_evidence_recheck_records,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_packet(tmp_path: Path) -> None:
    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == SHORT_EVIDENCE_RECHECK_READY
    assert payload["packet_recorded"] is False
    assert payload["packet_id"] is None
    assert payload["record_packet_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_packet=True,
        confirm_short_evidence_recheck="wrong",
        now=NOW,
    )

    assert payload["status"] == SHORT_EVIDENCE_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_short_evidence_recheck_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_packet_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        record_packet=True,
        confirm_short_evidence_recheck=CONFIRM_SHORT_EVIDENCE_RECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_short_evidence_recheck_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == SHORT_EVIDENCE_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SHORT_EVIDENCE_RECHECK_PACKET"
    assert config_path.read_text(encoding="utf-8") == before


def test_default_target_lane_is_8m_short_and_remains_paper(tmp_path: Path) -> None:
    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["target_family"]["symbol"] == "BTCUSDT"
    assert payload["target_family"]["timeframe"] == "8m"
    assert payload["target_family"]["direction"] == "short"
    assert payload["target_family"]["entry_mode"] == "ladder_close_50_618"
    assert payload["target_family"]["current_mode"] == "paper"


def test_fresh_capture_record_is_detected_and_latest_signal_id_surfaced(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")

    payload = build_short_evidence_recheck_packet(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["fresh_evidence"]["fresh_capture_records_count"] == 1
    assert payload["fresh_evidence"]["fresh_candidate_count"] == 1
    assert payload["fresh_evidence"]["latest_captured_signal_id"] == "fresh-short-1"
    assert payload["fresh_evidence"]["latest_capture_status"] == "SHORT_PAPER_EVIDENCE_CAPTURED"


def test_freshness_threshold_below_10_keeps_readiness_not_ready(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_good_outcomes(log_dir, 30)

    payload = build_short_evidence_recheck_packet(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["fresh_evidence"]["freshness_threshold_met"] is False
    assert payload["promotion_readiness"]["readiness"] != PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW
    assert payload["promotion_readiness"]["ready_for_operator_review"] is False


def test_mocked_fresh_captures_and_good_historical_evidence_can_be_ready() -> None:
    readiness = classify_short_promotion_readiness(
        target_family={
            "lane_key": LANE_8M_SHORT,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "current_mode": "paper",
        },
        fresh_evidence={"fresh_candidate_count": 10},
        historical_evidence={
            "paper_outcome_count": 30,
            "win_rate_pct": 60.0,
            "avg_pnl_pct": 0.05,
            "total_pnl_pct": 1.5,
            "fill_rate_pct": 100.0,
            "stop_count": 2,
        },
    )

    assert readiness == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW


def test_non_paper_or_non_short_target_does_not_promote() -> None:
    readiness = classify_short_promotion_readiness(
        target_family={"direction": "long", "current_mode": "tiny_live"},
        fresh_evidence={"fresh_candidate_count": 10},
        historical_evidence={"paper_outcome_count": 30, "win_rate_pct": 60.0, "avg_pnl_pct": 0.05, "stop_count": 0},
    )

    assert readiness == DO_NOT_PROMOTE


def test_no_lane_mode_apply_or_live_commands_emitted(tmp_path: Path) -> None:
    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "short-evidence-recheck-packet" in joined
    assert "short-paper-evidence-capture-loop" in joined
    assert "short-strategy-packet" in joined
    assert "full-spectrum-betrayal-short-review" in joined
    assert "live-connector-submit" not in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]


def test_config_written_false_and_safety_flags_clean(tmp_path: Path) -> None:
    payload = build_short_evidence_recheck_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["safety"]["config_written"] is False
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_order_payload_network_env_config_or_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "protective_preview") as protective_preview,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
        patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
        patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
    ):
        payload = build_short_evidence_recheck_packet(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            now=NOW,
        )

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    protective_preview.assert_not_called()
    submit_test_order.assert_not_called()
    submit_protective_test.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    build_signed_test_order_request.assert_not_called()
    build_signed_protective_order_requests.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["order_payload_created"] is False
    assert payload["safety"]["executable_payload_created"] is False
    assert payload["safety"]["protective_payload_created"] is False
    assert payload["safety"]["signed_request_created"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["protective_order_endpoint_called"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["global_live_flags_changed"] is False


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "short-evidence-recheck-packet",
            "--latest-captures",
            "10",
            "--latest-outcomes",
            "10",
            "--latest-signals",
            "20",
            "--latest-betrayal",
            "10",
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
    assert "fresh_evidence" in payload
    assert "promotion_readiness" in payload
    assert "short-evidence-recheck-packet" in help_result.stdout


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("13m", "long", "tiny_live"),
        _lane("44m", "long", "tiny_live"),
        _lane("8m", "long", "paper"),
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
        "max_daily_loss_pct": 0.1,
        "freshness_seconds": 60,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }


def _write_capture(log_dir: Path, signal_id: str) -> None:
    _append(
        log_dir / "short_paper_evidence_capture.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
            "capture_id": f"capture-{signal_id}",
            "recorded_at_utc": NOW.isoformat(),
            "status": "SHORT_PAPER_EVIDENCE_CAPTURED",
            "target_lane": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
            "paper_evidence_captured": True,
            "captured_signal_id": signal_id,
            "captured_lane_key": LANE_8M_SHORT,
            "safety": {"order_placed": False},
        },
    )


def _write_good_outcomes(log_dir: Path, count: int) -> None:
    for index in range(count):
        pnl_pct = 0.1 if index < 20 else -0.02
        _append(
            log_dir / "outcomes.ndjson",
            {
                "signal_id": f"{LANE_8M_SHORT}|{index}",
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "timestamp": (NOW - timedelta(minutes=count - index)).isoformat(),
                "evaluated_at": (NOW - timedelta(minutes=count - index - 1)).isoformat(),
                "fill_status": "filled",
                "outcome": "win" if pnl_pct > 0 else "loss",
                "pnl_pct": pnl_pct,
                "stop_hit": False,
            },
        )


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
