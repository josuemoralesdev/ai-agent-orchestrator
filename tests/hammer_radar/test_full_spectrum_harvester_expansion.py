from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE,
    FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED,
    FULL_SPECTRUM_HARVESTER_EXPANSION_RECORDED,
    FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED,
    LEDGER_FILENAME,
    build_full_spectrum_harvester_preview,
    build_full_spectrum_lane_candidates,
    capture_full_spectrum_paper_evidence_once,
    load_full_spectrum_harvester_records,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_22M_LONG = "BTCUSDT|22m|long|ladder_close_50_618"
LANE_55M_SHORT = "BTCUSDT|55m|short|ladder_close_50_618"
LANE_666M_SHORT = "BTCUSDT|666m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_full_spectrum_harvester_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_harvest_requested"] is False
    assert payload["harvest_recorded"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = capture_full_spectrum_paper_evidence_once(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_full_spectrum_harvest="wrong",
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_HARVESTER_EXPANSION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["harvest_recorded"] is False
    assert load_full_spectrum_harvester_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_harvest_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_full_spectrum_harvester_preview(
        log_dir=log_dir,
        config_path=config_path,
        record_harvest=True,
        confirm_full_spectrum_harvest=CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE,
        now=NOW,
    )
    records = load_full_spectrum_harvester_records(log_dir=log_dir, limit=0)

    assert payload["status"] == FULL_SPECTRUM_HARVESTER_EXPANSION_RECORDED
    assert payload["harvest_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FULL_SPECTRUM_HARVESTER_EXPANSION"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_expanded_scope_includes_r196_discovered_timeframes_and_unconfigured_lanes(tmp_path: Path) -> None:
    scope = build_full_spectrum_lane_candidates(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
    )
    discovered = {lane["lane_key"]: lane for lane in scope["discovered_unconfigured_paper_lanes"]}

    for timeframe in ("22m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D"):
        assert timeframe in scope["timeframes"]
    assert LANE_22M_LONG in discovered
    assert LANE_55M_SHORT in discovered
    assert LANE_666M_SHORT in discovered


def test_discovered_unconfigured_lanes_are_paper_only_and_configured_lanes_unchanged(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_full_spectrum_harvester_preview(log_dir=tmp_path / "logs", config_path=config_path, now=NOW)
    configured = {lane["lane_key"]: lane for lane in payload["scope"]["configured_paper_lanes"]}
    discovered = {lane["lane_key"]: lane for lane in payload["scope"]["discovered_unconfigured_paper_lanes"]}

    assert configured[LANE_4M_LONG]["mode"] == "paper"
    assert discovered[LANE_22M_LONG]["mode"] == "paper_discovered_unconfigured"
    assert discovered[LANE_22M_LONG]["config_write_allowed"] is False
    assert discovered[LANE_22M_LONG]["live_authorized"] is False
    assert before_config == config_path.read_text(encoding="utf-8")


def test_tiny_live_lanes_are_reference_only(tmp_path: Path) -> None:
    payload = build_full_spectrum_harvester_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    refs = {lane["lane_key"]: lane for lane in payload["scope"]["tiny_live_reference_lanes"]}

    assert refs[LANE_13M_LONG]["mode"] == "tiny_live"
    assert refs[LANE_13M_LONG]["reference_only"] is True
    assert refs[LANE_13M_LONG]["live_authorized"] is False
    assert refs[LANE_13M_LONG]["config_write_allowed"] is False


def test_fresh_full_spectrum_candidates_can_be_captured_from_configured_and_discovered_lanes(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=5), signal_id="8m-short")
    _write_signal(log_dir, "BTCUSDT", "22m", "long", NOW - timedelta(seconds=5), signal_id="22m-long")

    payload = capture_full_spectrum_paper_evidence_once(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_harvest=True,
        confirm_full_spectrum_harvest=CONFIRM_FULL_SPECTRUM_HARVEST_PHRASE,
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED
    assert {LANE_8M_SHORT, LANE_22M_LONG} <= set(payload["capture_summary"]["captured_lanes"])
    assert payload["capture_summary"]["total_captured"] == 2


def test_safe_commands_and_wma_anchor_note_are_future_only(tmp_path: Path) -> None:
    payload = build_full_spectrum_harvester_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["safe_run_commands"]["tmux_session"] == "r198-full-spectrum-harvest"
    assert "full-spectrum-harvester-expansion" in payload["safe_run_commands"]["preview_command"]
    assert payload["anchor_layer_future_note"]["wma_ma_anchor_layer_not_implemented"] is True
    assert payload["anchor_layer_future_note"]["future_phase"] == "R199_OR_LATER_WMA_MA_ANCHOR_LAYER_PREVIEW"
    assert payload["safety"]["wma_anchor_live_authorized"] is False


def test_no_env_config_mutation_no_binance_network_or_live_actions(tmp_path: Path) -> None:
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
        payload = build_full_spectrum_harvester_preview(log_dir=tmp_path / "logs", config_path=config_path, now=NOW)

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
            "full-spectrum-harvester-expansion",
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
    assert "full_spectrum_harvest_summary" in payload
    assert "full-spectrum-harvester-expansion" in help_result.stdout


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    _lane_config("13m", "long", "tiny_live"),
                    _lane_config("4m", "long", "paper"),
                    _lane_config("8m", "short", "paper"),
                ],
            }
        ),
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
        "freshness_seconds": 120,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }


def _write_signal(
    log_dir: Path,
    symbol: str,
    timeframe: str,
    direction: str,
    timestamp: datetime,
    *,
    signal_id: str,
) -> None:
    _append_json(
        log_dir / "signals.ndjson",
        {
            "signal_id": signal_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": "ladder_close_50_618",
            "timestamp": timestamp.isoformat(),
            "tradable": True,
        },
    )


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
