from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.strategy_lab_preview import (
    BETRAYAL_BLOCKED_PREVIEW_ONLY,
    CURRENT_TINY_LIVE_LANE,
    LEDGER_FILENAME,
    build_strategy_lab_preview,
    load_strategy_lab_preview_records,
)

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def test_strategy_lab_preview_writes_ndjson_and_never_allows_live_orders(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_preview(log_dir=log_dir, now=NOW)
    records = load_strategy_lab_preview_records(log_dir=log_dir, limit=10)

    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1
    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["real_order_forbidden"] is True
    for candidate in payload["preview_candidates"]:
        assert candidate["live_allowed"] is False
        assert candidate["final_command_available"] is False
        assert candidate["submit_allowed"] is False
        assert candidate["real_order_forbidden"] is True
        assert candidate["order_placed"] is False
        assert candidate["real_order_placed"] is False
        assert candidate["execution_attempted"] is False
        assert candidate["binance_order_endpoint_called"] is False
        assert candidate["binance_test_order_endpoint_called"] is False


def test_current_live_qualified_lanes_are_preview_only_not_final_commands(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_preview(log_dir=log_dir, now=NOW, write=False)
    by_lane = {row["lane_key"]: row for row in payload["preview_candidates"]}

    for lane in (
        CURRENT_TINY_LIVE_LANE,
        "BTCUSDT|44m|short|ladder_close_50_618",
        "BTCUSDT|55m|long|ladder_close_50_618",
    ):
        assert lane in by_lane
        assert by_lane[lane]["watch_category"] == "LIVE_QUALIFIED"
        assert by_lane[lane]["final_command_available"] is False
        assert by_lane[lane]["submit_allowed"] is False
        assert by_lane[lane]["live_allowed"] is False

    assert by_lane[CURRENT_TINY_LIVE_LANE]["recommended_lab_action"] == "KEEP_TINY_LIVE_WAIT"
    assert by_lane["BTCUSDT|44m|short|ladder_close_50_618"]["recommended_lab_action"] == "EXPANSION_PREVIEW_ONLY"


def test_near_miss_lanes_are_incubator_or_blocked_preview_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_preview(log_dir=log_dir, now=NOW, write=False)
    by_lane = {row["lane_key"]: row for row in payload["preview_candidates"]}

    assert by_lane["BTCUSDT|22m|long|ladder_close_50_618"]["watch_category"] == "NEAR_MISS_INCUBATOR"
    assert by_lane["BTCUSDT|22m|long|ladder_close_50_618"]["recommended_lab_action"] == "STRATEGY_LAB_REVIEW"
    assert by_lane["BTCUSDT|8m|short|ladder_close_50_618"]["watch_category"] == "NEAR_MISS_INCUBATOR"
    assert by_lane["BTCUSDT|8m|short|ladder_close_50_618"]["live_allowed"] is False


def test_betrayal_inverse_preview_remains_blocked_from_tiny_live(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    betrayal_status = {
        "ledger_path": str(log_dir / "betrayal_true_paper_outcomes.ndjson"),
        "identity_summaries": [
            {
                "betrayal_paper_signal_id": "betrayal-1",
                "symbol": "BTCUSDT",
                "timeframe": "222m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "true_paper_outcomes_count": 12,
                "paper_win_rate_pct": 66.0,
                "paper_avg_pnl_pct": 0.2,
                "paper_total_pnl_pct": 2.4,
            }
        ],
    }

    with patch(
        "src.app.hammer_radar.operator.strategy_lab_preview.build_betrayal_paper_outcome_status",
        return_value=betrayal_status,
    ):
        payload = build_strategy_lab_preview(log_dir=log_dir, now=NOW, write=False)

    row = payload["betrayal_preview_candidates"][0]
    assert row["watch_category"] == "BETRAYAL_INVERSE_PREVIEW"
    assert row["betrayal_gate_decision"] == BETRAYAL_BLOCKED_PREVIEW_ONLY
    assert row["live_allowed"] is False
    assert row["final_command_available"] is False
    assert row["submit_allowed"] is False
    assert row["real_order_forbidden"] is True
    rendered = json.dumps(payload)
    assert "BETRAYAL_LIVE_ALLOWED" not in rendered


def test_no_secret_or_binance_order_surfaces_are_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_strategy_lab_preview(log_dir=log_dir, now=NOW, write=False)

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["secret_values_in_output"] is False


def test_direct_module_and_inspect_cli_exist(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "."}
    root = Path(__file__).resolve().parents[2]
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.strategy_lab_preview", "--help"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    inspect_result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "strategy-lab-preview",
            "--no-write",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--log-dir" in help_result.stdout
    payload = json.loads(inspect_result.stdout)
    assert payload["event_type"] == "R304_STRATEGY_LAB_PREVIEW"
    assert payload["submit_allowed"] is False


def _seed_strategy_status(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "qualified_candidate_watch": {
            "live_qualified_lanes": [
                _lane("44m", "long", 58.57, 70),
                _lane("44m", "short", 62.0, 40),
                _lane("55m", "long", 62.0, 40),
            ],
            "near_miss_incubator_lanes": [
                _lane("22m", "long", 54.0, 35),
                _lane("22m", "short", 53.5, 32),
                _lane("8m", "short", 53.33, 30),
            ],
            "paper_only_lanes": [_lane("13m", "long", 47.27, 55)],
        }
    }
    with (log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _lane(timeframe: str, direction: str, win_rate_pct: float, sample_count: int) -> dict[str, object]:
    avg_pnl_pct = 0.1
    return {
        "strategy_key": f"BTCUSDT|{timeframe}|{direction}|ladder_close_50_618",
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "total_pnl_pct": round(avg_pnl_pct * sample_count, 4),
    }
