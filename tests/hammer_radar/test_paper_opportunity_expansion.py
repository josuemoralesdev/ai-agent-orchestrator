from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.paper_opportunity_expansion import (
    CONFIRM_PAPER_OPPORTUNITY_EXPANSION_PHRASE,
    LEDGER_FILENAME,
    PAPER_OPPORTUNITY_EXPANSION_APPLIED,
    PAPER_OPPORTUNITY_EXPANSION_PREVIEW,
    PAPER_OPPORTUNITY_EXPANSION_REJECTED,
    SAFETY,
    apply_paper_opportunity_expansion_plan,
    build_default_paper_expansion_lanes,
    build_paper_opportunity_expansion_preview,
    build_recent_btcusdt_timeframe_direction_distribution,
    load_paper_opportunity_expansion_records,
    validate_paper_expansion_plan,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"


def test_default_expansion_covers_required_lanes_and_risk_limits() -> None:
    lanes = build_default_paper_expansion_lanes()
    by_key = {lane["lane_key"]: lane for lane in lanes}

    assert set(by_key) == {
        "BTCUSDT|4m|long|ladder_close_50_618",
        "BTCUSDT|4m|short|ladder_close_50_618",
        "BTCUSDT|8m|long|ladder_close_50_618",
        "BTCUSDT|8m|short|ladder_close_50_618",
        "BTCUSDT|13m|long|ladder_close_50_618",
        "BTCUSDT|13m|short|ladder_close_50_618",
        "BTCUSDT|44m|long|ladder_close_50_618",
        "BTCUSDT|44m|short|ladder_close_50_618",
    }
    assert by_key["BTCUSDT|4m|short|ladder_close_50_618"]["mode"] == "paper"
    assert by_key["BTCUSDT|8m|short|ladder_close_50_618"]["max_daily_loss_pct"] == 0.15
    assert by_key["BTCUSDT|13m|short|ladder_close_50_618"]["freshness_seconds"] == 120
    assert by_key["BTCUSDT|44m|short|ladder_close_50_618"]["cooldown_after_loss_minutes"] == 180
    assert all(lane["max_daily_trades"] == 1 for lane in lanes)
    assert all(lane["require_protective_orders"] is True for lane in lanes)


def test_preview_writes_no_config_or_ledger(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_paper_opportunity_expansion_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_default_expansion=True,
        now=NOW,
    )

    assert payload["status"] == PAPER_OPPORTUNITY_EXPANSION_PREVIEW
    assert payload["apply_requested"] is False
    assert payload["config_written"] is False
    assert payload["expansion_recorded"] is False
    assert payload["safety"]["config_written"] is False
    assert config_path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_apply(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_paper_opportunity_expansion_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_default_expansion=True,
        apply=True,
        confirm_paper_expansion="wrong",
        now=NOW,
    )

    assert payload["status"] == PAPER_OPPORTUNITY_EXPANSION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["config_written"] is False
    assert config_path.read_text(encoding="utf-8") == before


def test_exact_confirmation_applies_only_paper_lanes_in_temp_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")

    payload = build_paper_opportunity_expansion_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_default_expansion=True,
        apply=True,
        record_expansion=True,
        confirm_paper_expansion=CONFIRM_PAPER_OPPORTUNITY_EXPANSION_PHRASE,
        now=NOW,
    )
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    by_key = {_lane_key(lane): lane for lane in raw["lanes"]}
    records = load_paper_opportunity_expansion_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == PAPER_OPPORTUNITY_EXPANSION_APPLIED
    assert payload["config_written"] is True
    assert payload["safety"]["config_written"] is True
    assert payload["expansion_recorded"] is True
    assert len(records) == 1
    assert by_key[LANE_13M]["mode"] == "tiny_live"
    assert by_key[LANE_44M]["mode"] == "tiny_live"
    assert by_key["BTCUSDT|4m|short|ladder_close_50_618"]["mode"] == "paper"
    assert by_key["BTCUSDT|8m|short|ladder_close_50_618"]["mode"] == "paper"
    assert by_key["BTCUSDT|13m|short|ladder_close_50_618"]["mode"] == "paper"
    assert by_key["BTCUSDT|44m|short|ladder_close_50_618"]["mode"] == "paper"
    assert all(lane["mode"] != "tiny_live" for key, lane in by_key.items() if key not in {LANE_13M, LANE_44M})


def test_existing_tiny_live_modes_are_preserved_and_new_lanes_are_paper(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    payload = build_paper_opportunity_expansion_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_default_expansion=True,
        now=NOW,
    )

    preserve = {lane["lane_key"]: lane for lane in payload["lanes_to_preserve"]}
    add = {lane["lane_key"]: lane for lane in payload["lanes_to_add"]}

    assert preserve[LANE_13M]["mode"] == "tiny_live"
    assert preserve[LANE_44M]["mode"] == "tiny_live"
    assert all(lane["mode"] == "paper" for lane in add.values())
    assert all(not (lane["direction"] == "short" and lane["mode"] == "tiny_live") for lane in add.values())
    assert payload["expected_after_apply"]["existing_tiny_live_lanes_preserved"] is True
    assert payload["expected_after_apply"]["new_lanes_are_paper_only"] is True


def test_forbidden_changes_are_blocked(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    validation = validate_paper_expansion_plan(
        existing_lanes=[],
        proposed_lanes=[
            {
                "symbol": "BTCUSDT",
                "timeframe": "4m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "tiny_live",
                "max_daily_trades": 1,
                "max_daily_loss_pct": 0.10,
                "freshness_seconds": 30,
                "cooldown_after_loss_minutes": 120,
                "require_protective_orders": True,
            }
        ],
    )
    result = apply_paper_opportunity_expansion_plan(config_path=config_path, lanes_to_add=validation["lanes_to_add"])

    assert validation["plan_valid"] is False
    assert validation["lanes_to_add"] == []
    assert validation["forbidden_changes_blocked"]
    assert result["config_written"] is False


def test_distribution_counts_long_short_and_timeframes(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "short")
    _write_signal(log_dir, "BTCUSDT", "13m", "long")
    _write_signal(log_dir, "ETHUSDT", "13m", "short")
    _write_scan(log_dir, "BTCUSDT", "8m", "long")

    payload = build_recent_btcusdt_timeframe_direction_distribution(log_dir=log_dir, now=NOW)

    assert payload["long_signal_count"] == 1
    assert payload["short_signal_count"] == 1
    assert payload["by_timeframe_direction"]["4m|short"] == 1
    assert payload["by_timeframe_direction"]["8m|long"] == 1
    assert "13m" in payload["scanned_timeframes_seen"]


def test_safety_flags_clean_and_no_binance_network_env_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
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
        payload = build_paper_opportunity_expansion_preview(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            include_default_expansion=True,
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
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["global_live_flags_changed"] is False
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "paper-opportunity-expansion",
            "--latest-signals",
            "10",
            "--latest-scans",
            "20",
            "--include-default-expansion",
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
    assert payload["status"] == PAPER_OPPORTUNITY_EXPANSION_PREVIEW
    assert "lanes_to_add" in payload
    assert "recent_distribution" in payload
    assert "paper-opportunity-expansion" in help_result.stdout


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "notes": ["test config"],
                "lanes": [
                    _lane("13m", "long", "tiny_live", 0.25, 120, 120),
                    _lane("44m", "long", "tiny_live", 0.25, 300, 180),
                    _lane("8m", "long", "paper", 0.15, 60, 120),
                    _lane("4m", "long", "paper", 0.10, 30, 120),
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _lane(
    timeframe: str,
    direction: str,
    mode: str,
    max_daily_loss_pct: float,
    freshness_seconds: int,
    cooldown_after_loss_minutes: int,
) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": mode,
        "max_daily_trades": 1,
        "max_daily_loss_pct": max_daily_loss_pct,
        "freshness_seconds": freshness_seconds,
        "cooldown_after_loss_minutes": cooldown_after_loss_minutes,
        "require_protective_orders": True,
    }


def _lane_key(lane: dict[str, object]) -> str:
    return "|".join(
        [
            str(lane["symbol"]),
            str(lane["timeframe"]),
            str(lane["direction"]),
            str(lane["entry_mode"]),
        ]
    )


def _write_signal(log_dir: Path, symbol: str, timeframe: str, direction: str) -> None:
    _append(
        log_dir / "signals.ndjson",
        {
            "signal_id": f"{symbol}-{timeframe}-{direction}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "timestamp": NOW.isoformat(),
        },
    )


def _write_scan(log_dir: Path, symbol: str, timeframe: str, direction: str) -> None:
    _append(
        log_dir / "multi_symbol_paper_scans.ndjson",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "generated_at": NOW.isoformat(),
        },
    )


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
