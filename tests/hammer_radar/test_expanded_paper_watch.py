from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.expanded_paper_watch import (
    CONFIRM_EXPANDED_PAPER_WATCH_RECORDING_PHRASE,
    EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL,
    EXPANDED_PAPER_WATCH_RECORDED,
    EXPANDED_PAPER_WATCH_REJECTED,
    LEDGER_FILENAME,
    build_expanded_paper_distribution,
    build_expanded_paper_lane_scope,
    build_expanded_paper_watch_preview,
    load_expanded_paper_watch_records,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")

    payload = build_expanded_paper_watch_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        all_paper_lanes=True,
        include_tiny_live_targets_as_observed=True,
        now=NOW,
    )

    assert payload["record_watch_requested"] is False
    assert payload["watch_recorded"] is False
    assert payload["watch_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_expanded_paper_watch_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        all_paper_lanes=True,
        record_watch=True,
        confirm_expanded_paper_watch="wrong",
        now=NOW,
    )

    assert payload["status"] == EXPANDED_PAPER_WATCH_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["watch_recorded"] is False
    assert load_expanded_paper_watch_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_watch_only(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_expanded_paper_watch_preview(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        all_paper_lanes=True,
        include_tiny_live_targets_as_observed=True,
        record_watch=True,
        confirm_expanded_paper_watch=CONFIRM_EXPANDED_PAPER_WATCH_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_expanded_paper_watch_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == EXPANDED_PAPER_WATCH_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["watch_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "EXPANDED_PAPER_WATCH"
    assert records[0]["safety"]["order_placed"] is False
    assert config_path.read_text(encoding="utf-8") == before


def test_paper_scope_includes_long_short_and_tiny_live_observed_but_not_mutated(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
    before = json.loads(config_path.read_text(encoding="utf-8"))

    scope = build_expanded_paper_lane_scope(
        config_path=config_path,
        all_paper_lanes=True,
        include_tiny_live_targets_as_observed=True,
    )
    paper_keys = {lane["lane_key"] for lane in scope["expanded_scope"]["paper_lanes"]}
    tiny_keys = {lane["lane_key"] for lane in scope["expanded_scope"]["tiny_live_lanes_observed_but_not_changed"]}

    assert "long" in scope["expanded_scope"]["directions_covered"]
    assert "short" in scope["expanded_scope"]["directions_covered"]
    assert "BTCUSDT|4m|long|ladder_close_50_618" in paper_keys
    assert "BTCUSDT|13m|short|ladder_close_50_618" in paper_keys
    assert {LANE_13M_LONG, LANE_44M_LONG} == tiny_keys
    assert json.loads(config_path.read_text(encoding="utf-8")) == before


def test_short_lanes_remain_paper_and_no_new_tiny_live_created(tmp_path: Path) -> None:
    payload = build_expanded_paper_watch_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        all_paper_lanes=True,
        include_tiny_live_targets_as_observed=True,
        now=NOW,
    )
    state = payload["lane_config_state"]

    assert state["BTCUSDT|4m|short|ladder_close_50_618"]["mode"] == "paper"
    assert state["BTCUSDT|8m|short|ladder_close_50_618"]["mode"] == "paper"
    assert state["BTCUSDT|13m|short|ladder_close_50_618"]["mode"] == "paper"
    assert state["BTCUSDT|44m|short|ladder_close_50_618"]["mode"] == "paper"
    assert all(
        row["mode"] != "tiny_live" or lane_key in {LANE_13M_LONG, LANE_44M_LONG}
        for lane_key, row in state.items()
    )


def test_candidate_distribution_counts_by_timeframe_direction_and_fresh_stale_lanes(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    scope = build_expanded_paper_lane_scope(
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        all_paper_lanes=True,
    )
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5))
    _write_signal(log_dir, "BTCUSDT", "8m", "long", NOW - timedelta(seconds=90))
    _write_scan(log_dir, "BTCUSDT", "13m", "short", NOW - timedelta(seconds=60))

    payload = build_expanded_paper_distribution(
        log_dir=log_dir,
        paper_lanes=scope["paper_lanes"],
        now=NOW,
    )

    assert payload["by_timeframe_direction"]["4m|short"] == 1
    assert payload["by_timeframe_direction"]["8m|long"] == 1
    assert payload["by_timeframe_direction"]["13m|short"] == 1
    assert payload["fresh_by_lane"]["BTCUSDT|4m|short|ladder_close_50_618"] == 1
    assert payload["fresh_by_lane"]["BTCUSDT|13m|short|ladder_close_50_618"] == 1
    assert payload["stale_by_lane"]["BTCUSDT|8m|long|ladder_close_50_618"] == 1


def test_paper_opportunity_summary_identifies_fresh_lane_family(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "4m", "short", NOW - timedelta(seconds=5))

    payload = build_expanded_paper_watch_preview(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        all_paper_lanes=True,
        now=NOW,
    )

    assert payload["status"] == EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL
    assert payload["paper_opportunity_summary"]["fresh_paper_candidates_count"] == 1
    assert payload["paper_opportunity_summary"]["short_paper_candidates_count"] == 1
    assert payload["paper_opportunity_summary"]["long_paper_candidates_count"] == 0
    assert payload["paper_opportunity_summary"]["best_next_paper_lane_family"] == "4m|short"


def test_safe_commands_contain_no_live_submit_order_or_global_arming(tmp_path: Path) -> None:
    payload = build_expanded_paper_watch_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        all_paper_lanes=True,
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "expanded-paper-watch" in joined
    assert "candidate-source-freshness-audit" in joined
    assert "paper-opportunity-expansion" in joined
    assert "live-connector-submit" not in joined
    assert "order endpoint" not in joined
    assert "global live flag arming" not in joined


def test_safety_flags_clean_and_no_binance_order_payload_network_env_config_or_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
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
        payload = build_expanded_paper_watch_preview(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            all_paper_lanes=True,
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
            "expanded-paper-watch",
            "--latest-signals",
            "10",
            "--latest-scans",
            "20",
            "--all-paper-lanes",
            "--include-tiny-live-targets-as-observed",
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
    assert "expanded_scope" in payload
    assert "candidate_distribution" in payload
    assert "paper_opportunity_summary" in payload
    assert "expanded-paper-watch" in help_result.stdout


def _write_expanded_config(path: Path) -> Path:
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
                    _lane("4m", "long", "paper", 0.10, 30, 120),
                    _lane("8m", "long", "paper", 0.15, 60, 120),
                    _lane("4m", "short", "paper", 0.10, 30, 120),
                    _lane("8m", "short", "paper", 0.15, 60, 120),
                    _lane("13m", "short", "paper", 0.20, 120, 120),
                    _lane("44m", "short", "paper", 0.20, 300, 180),
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


def _write_signal(log_dir: Path, symbol: str, timeframe: str, direction: str, timestamp: datetime) -> None:
    _append(
        log_dir / "signals.ndjson",
        {
            "signal_id": f"{symbol}-{timeframe}-{direction}-{timestamp.isoformat()}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "timestamp": timestamp.isoformat(),
        },
    )


def _write_scan(log_dir: Path, symbol: str, timeframe: str, direction: str, timestamp: datetime) -> None:
    _append(
        log_dir / "multi_symbol_paper_scans.ndjson",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "generated_at": timestamp.isoformat(),
        },
    )


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
