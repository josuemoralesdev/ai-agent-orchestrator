from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_paper_capture_harvester import (
    CONFIRM_MULTI_LANE_HARVEST_PHRASE,
    LEDGER_FILENAME,
    MULTI_LANE_PAPER_HARVESTER_CAPTURED,
    MULTI_LANE_PAPER_HARVESTER_RECORDED,
    MULTI_LANE_PAPER_HARVESTER_REJECTED,
    build_lane_capture_counts,
    build_multi_lane_harvest_scope,
    build_multi_lane_paper_capture_harvester_preview,
    build_next_lane_candidate_recommendation,
    capture_multi_lane_paper_evidence_once,
    load_multi_lane_harvester_records,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_4M_SHORT = "BTCUSDT|4m|short|ladder_close_50_618"
LANE_8M_LONG = "BTCUSDT|8m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_SHORT = "BTCUSDT|13m|short|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_multi_lane_paper_capture_harvester_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_harvest_requested"] is False
    assert payload["harvest_recorded"] is False
    assert payload["watch_started"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = capture_multi_lane_paper_evidence_once(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_multi_lane_harvest="wrong",
        now=NOW,
    )

    assert payload["status"] == MULTI_LANE_PAPER_HARVESTER_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["harvest_recorded"] is False
    assert load_multi_lane_harvester_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_multi_lane_paper_capture_harvester_preview(
        log_dir=log_dir,
        config_path=config_path,
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )
    records = load_multi_lane_harvester_records(log_dir=log_dir, limit=0)

    assert payload["status"] == MULTI_LANE_PAPER_HARVESTER_RECORDED
    assert payload["harvest_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "MULTI_LANE_PAPER_CAPTURE_HARVESTER"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_scope_includes_expanded_paper_lanes_and_separates_tiny_live(tmp_path: Path) -> None:
    scope = build_multi_lane_harvest_scope(config_path=_write_config(tmp_path / "lane_controls.json"))
    paper_keys = {lane["lane_key"] for lane in scope["paper_lanes"]}
    observed_keys = {lane["lane_key"] for lane in scope["observed_tiny_live_lanes"]}

    assert {LANE_4M_LONG, LANE_4M_SHORT, LANE_8M_LONG, LANE_8M_SHORT, LANE_13M_SHORT, LANE_44M_SHORT} <= paper_keys
    assert observed_keys == {LANE_13M_LONG, LANE_44M_LONG}
    assert scope["directions"] == ["long", "short"]


def test_fresh_candidates_across_multiple_paper_lanes_can_be_captured(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "long", NOW - timedelta(seconds=5), signal_id="4m-long")
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=5), signal_id="8m-short")
    _write_scan(log_dir, "BTCUSDT", "13m", "short", NOW - timedelta(seconds=10), signal_id="13m-short")

    payload = capture_multi_lane_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )

    assert payload["status"] == MULTI_LANE_PAPER_HARVESTER_CAPTURED
    assert payload["capture_summary"]["total_captured"] == 3
    assert {LANE_4M_LONG, LANE_8M_SHORT, LANE_13M_SHORT} <= set(payload["capture_summary"]["captured_lanes"])


def test_stale_wrong_symbol_and_wrong_entry_mode_are_not_captured(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=90), signal_id="stale")
    _write_signal(log_dir, "ETHUSDT", "4m", "short", NOW - timedelta(seconds=5), signal_id="wrong-symbol")
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5), signal_id="wrong-entry", entry_mode="market")

    payload = capture_multi_lane_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )

    assert payload["capture_summary"]["total_captured"] == 0
    assert payload["capture_summary"]["stale_by_lane"][LANE_4M_SHORT] == 1
    assert LANE_4M_SHORT not in payload["capture_summary"]["captured_lanes"]


def test_missing_entry_mode_is_normalized_when_lane_tuple_matches(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5), signal_id="normalized", entry_mode=None)

    payload = capture_multi_lane_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )

    assert payload["capture_summary"]["total_captured"] == 1
    assert payload["capture_summary"]["captured_candidates"][0]["entry_mode"] == "ladder_close_50_618"


def test_max_captures_per_iteration_respected(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(5):
        _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5), signal_id=f"fresh-{index}")

    payload = capture_multi_lane_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        max_captures_per_iteration=2,
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )

    assert payload["capture_summary"]["total_captured"] == 2


def test_lane_capture_counts_include_8m_short_and_other_lanes(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5), signal_id="4m-short")
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=5), signal_id="8m-short")
    capture_multi_lane_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_multi_lane_harvest=CONFIRM_MULTI_LANE_HARVEST_PHRASE,
        now=NOW,
    )

    counts = build_lane_capture_counts(
        log_dir=log_dir,
        scope=build_multi_lane_harvest_scope(config_path=tmp_path / "lane_controls.json"),
        required_fresh_capture_count=10,
    )

    assert counts[LANE_8M_SHORT]["fresh_capture_count"] == 1
    assert counts[LANE_4M_SHORT]["fresh_capture_count"] == 1
    assert counts[LANE_8M_SHORT]["threshold_met"] is False


def test_lead_lane_recommendation_works() -> None:
    recommendation = build_next_lane_candidate_recommendation(
        lane_capture_counts={
            LANE_8M_SHORT: {"fresh_capture_count": 3},
            LANE_4M_SHORT: {"fresh_capture_count": 5},
        },
        fresh_by_lane={LANE_4M_SHORT: 2},
    )

    assert recommendation["lead_lane"] == LANE_4M_SHORT
    assert recommendation["eight_m_short_still_lead"] is False
    assert recommendation["new_lane_candidate_emerged"] is True


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
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
        payload = build_multi_lane_paper_capture_harvester_preview(log_dir=tmp_path / "logs", config_path=config_path, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    assert safety["env_written"] is False
    assert safety["config_written"] is False
    assert safety["lane_config_written"] is False
    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["binance_order_endpoint_called"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-paper-harvester",
            "--latest-signals",
            "10",
            "--latest-scans",
            "20",
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
    assert "capture_summary" in payload
    assert "lane_capture_counts" in payload
    assert "multi-lane-paper-harvester" in help_result.stdout


def _write_signal(
    log_dir: Path,
    symbol: str,
    timeframe: str,
    direction: str,
    generated_at: datetime,
    *,
    signal_id: str,
    entry_mode: str | None = "ladder_close_50_618",
) -> None:
    record = {
        "signal_id": signal_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "generated_at": generated_at.isoformat(),
        "tradable": True,
    }
    if entry_mode is not None:
        record["entry_mode"] = entry_mode
    _append_json(log_dir / "signals.ndjson", record)


def _write_scan(log_dir: Path, symbol: str, timeframe: str, direction: str, generated_at: datetime, *, signal_id: str) -> None:
    _append_json(
        log_dir / "multi_symbol_paper_scans.ndjson",
        {
            "signal_id": signal_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": "ladder_close_50_618",
            "generated_at": generated_at.isoformat(),
            "tradable": True,
        },
    )


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("13m", "long", "tiny_live", 120),
        _lane("44m", "long", "tiny_live", 300),
        _lane("4m", "long", "paper", 30),
        _lane("4m", "short", "paper", 30),
        _lane("8m", "long", "paper", 60),
        _lane("8m", "short", "paper", 60),
        _lane("13m", "short", "paper", 120),
        _lane("44m", "short", "paper", 300),
    ]
    path.write_text(json.dumps({"schema_version": "1.0", "default_mode": "disabled", "lanes": lanes}), encoding="utf-8")
    return path


def _lane(timeframe: str, direction: str, mode: str, freshness_seconds: int) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": mode,
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.1,
        "freshness_seconds": freshness_seconds,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }
