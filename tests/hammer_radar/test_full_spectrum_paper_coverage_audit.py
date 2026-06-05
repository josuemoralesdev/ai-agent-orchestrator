from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.full_spectrum_paper_coverage_audit import (
    CONFIRM_FULL_SPECTRUM_PAPER_AUDIT_RECORDING_PHRASE,
    FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDED,
    FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_REJECTED,
    LEDGER_FILENAME,
    ORIGIN_REGISTERED_NO_DETECTOR,
    OUTCOMES_PRESENT_NOT_WATCHED,
    SIGNALS_PRESENT_NOT_CONFIGURED,
    build_full_spectrum_paper_coverage_audit,
    load_full_spectrum_paper_coverage_audit_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_22M_LONG = "BTCUSDT|22m|long|ladder_close_50_618"
LANE_ETH_55M_SHORT = "ETHUSDT|55m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_audit_requested"] is False
    assert payload["audit_recorded"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_audit=True,
        confirm_full_spectrum_paper_audit="wrong",
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["audit_recorded"] is False
    assert load_full_spectrum_paper_coverage_audit_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_audit_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        record_audit=True,
        confirm_full_spectrum_paper_audit=CONFIRM_FULL_SPECTRUM_PAPER_AUDIT_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_full_spectrum_paper_coverage_audit_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == FULL_SPECTRUM_PAPER_COVERAGE_AUDIT_RECORDED
    assert payload["audit_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FULL_SPECTRUM_PAPER_COVERAGE_AUDIT"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_configured_paper_and_tiny_live_reference_lanes_are_listed(tmp_path: Path) -> None:
    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    lanes = {row["lane_key"]: row for row in payload["lane_coverage_matrix"]}

    assert payload["coverage_summary"]["paper_lanes_count"] == 2
    assert payload["coverage_summary"]["tiny_live_reference_lanes_count"] == 1
    assert lanes[LANE_8M_SHORT]["mode"] == "paper"
    assert lanes[LANE_13M_LONG]["mode"] == "tiny_live"
    assert lanes[LANE_13M_LONG]["reference_only"] is True


def test_timeframes_symbols_and_signal_blind_spots_are_discovered(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _append_json(log_dir / "signals.ndjson", _signal("BTCUSDT", "22m", "long", signal_origin="breakout_retest"))
    _append_json(log_dir / "multi_symbol_paper_scans.ndjson", _scan("ETHUSDT", "55m", "short"))

    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert "22m" in payload["coverage_summary"]["timeframes_found"]
    assert "55m" in payload["coverage_summary"]["timeframes_found"]
    assert "ETHUSDT" in payload["symbol_coverage_matrix"]
    assert LANE_22M_LONG in payload["blind_spot_report"]["signals_present_not_configured"]
    assert LANE_ETH_55M_SHORT in payload["blind_spot_report"]["signals_present_not_configured"]


def test_registered_origins_without_detectors_are_flagged(tmp_path: Path) -> None:
    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["signal_origin_coverage_matrix"]["three_white_soldiers"]["coverage_status"] == ORIGIN_REGISTERED_NO_DETECTOR
    assert "bearish_engulfing" in payload["blind_spot_report"]["origins_registered_without_detector"]


def test_paper_outcomes_without_watcher_coverage_are_flagged(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _append_json(log_dir / "outcomes.ndjson", {"symbol": "BTCUSDT", "timeframe": "8m", "direction": "short", "entry_mode": "ladder_close_50_618", "signal_id": "BTCUSDT|8m|short|t", "pnl_pct": 0.1})

    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    row = _lane(payload, LANE_8M_SHORT)

    assert row["coverage_status"] == OUTCOMES_PRESENT_NOT_WATCHED
    assert LANE_8M_SHORT in payload["blind_spot_report"]["paper_outcomes_without_current_watcher"]


def test_8m_short_is_recognized_as_covered_and_ranked_when_fixtures_include_it(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _append_json(log_dir / "multi_lane_paper_harvester.ndjson", {"capture_summary": {"fresh_by_lane": {LANE_8M_SHORT: 3}, "stale_by_lane": {}, "observed_tiny_live_by_lane": {}}})
    _append_json(log_dir / "multi_lane_evidence_rankings.ndjson", {"ranked_lanes": [{"lane_key": LANE_8M_SHORT}]})

    payload = build_full_spectrum_paper_coverage_audit(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    row = _lane(payload, LANE_8M_SHORT)

    assert row["harvester_coverage"] == "covered"
    assert row["ranked"] is True
    assert row["coverage_status"] == "COVERED_ACTIVE"


def test_safety_blocks_env_config_network_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_full_spectrum_paper_coverage_audit(log_dir=tmp_path / "logs", config_path=config_path, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "full-spectrum-paper-coverage-audit",
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
    assert "coverage_summary" in payload
    assert "full-spectrum-paper-coverage-audit" in help_result.stdout


def _lane(payload: dict[str, object], lane_key: str) -> dict[str, object]:
    return next(row for row in payload["lane_coverage_matrix"] if row["lane_key"] == lane_key)


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    _lane_config("13m", "long", "tiny_live"),
                    _lane_config("8m", "long", "paper"),
                    _lane_config("8m", "short", "paper"),
                ],
            }
        ),
        encoding="utf-8",
    )
    (path.parent / "tiny_live_risk_contracts.json").write_text(
        json.dumps({"risk_contracts": [{"symbol": "BTCUSDT", "timeframe": "13m", "direction": "long"}]}),
        encoding="utf-8",
    )
    return path


def _lane_config(timeframe: str, direction: str, mode: str) -> dict[str, object]:
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


def _signal(symbol: str, timeframe: str, direction: str, *, signal_origin: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "signal_origin": signal_origin,
        "signal_id": f"{symbol}|{timeframe}|{direction}|2026-06-04T00:00:00+00:00",
    }


def _scan(symbol: str, timeframe: str, direction: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "scan_id": f"{symbol}-{timeframe}-{direction}",
    }
