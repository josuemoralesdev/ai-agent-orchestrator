from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.strategy_lab_variant_test_pack import (
    CURRENT_TINY_LIVE_LANE,
    DIRECT_PAPER_EVIDENCE,
    EVENT_TYPE,
    INSUFFICIENT_DIRECT_VARIANT_EVIDENCE,
    LEDGER_FILENAME,
    build_strategy_lab_variant_test_pack,
    load_strategy_lab_variant_test_pack_records,
)

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def test_variant_pack_writes_preview_only_packet_and_locks_safety(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW)
    records = load_strategy_lab_variant_test_pack_records(log_dir=log_dir, limit=10)

    assert payload["event_type"] == EVENT_TYPE
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1
    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["global_kill_switch"] is True
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False
    for row in payload["variant_candidates"]:
        assert row["submit_allowed"] is False
        assert row["final_command_available"] is False
        assert row["order_placed"] is False
        assert row["real_order_placed"] is False
        assert row["execution_attempted"] is False


def test_current_and_top_r304_lanes_are_included(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW, write=False)
    family_lanes = {row["lane_key"] for row in payload["candidate_families"]}
    variant_lanes = {row["lane_key"] for row in payload["variant_candidates"]}

    for lane in (
        CURRENT_TINY_LIVE_LANE,
        "BTCUSDT|44m|short|ladder_close_50_618",
        "BTCUSDT|55m|long|ladder_close_50_618",
        "BTCUSDT|44m|short|ladder_382_50_618",
        "BTCUSDT|44m|short|ladder_22_44_22",
        "BTCUSDT|44m|long|ladder_382_50_618",
        "BTCUSDT|88m|long|ladder_382_50_618",
        "BTCUSDT|55m|long|market_close",
        "BTCUSDT|44m|long|ladder_22_44_22",
    ):
        assert lane in family_lanes
        assert lane in variant_lanes

    assert payload["current_tiny_live_lane_status"]["lane_key"] == CURRENT_TINY_LIVE_LANE
    assert payload["current_tiny_live_lane_status"]["tiny_live_lane_unchanged"] is True


def test_missing_direct_variant_evidence_is_not_invented(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW, write=False)
    missing_rows = [
        row
        for row in payload["variant_candidates"]
        if row["lane_key"] == "BTCUSDT|44m|long|fib_650"
    ]

    assert missing_rows
    row = missing_rows[0]
    assert row["evidence_status"] == INSUFFICIENT_DIRECT_VARIANT_EVIDENCE
    assert row["direct_sample_count"] == 0
    assert row["win_rate_pct"] is None
    assert row["avg_pnl_pct"] is None
    assert row["variant_score_status"] == "NEEDS_PAPER_CAPTURE"
    assert row["recommended_lab_action"] == "CAPTURE_VARIANT_EVIDENCE"


def test_direct_variant_rankings_are_lab_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW, write=False)

    assert payload["top_variant_candidates"]
    assert payload["top_variant_candidates"][0]["evidence_status"] == DIRECT_PAPER_EVIDENCE
    assert payload["top_variant_candidates"][0]["strategy_lab_score"] > 0
    assert payload["top_variant_candidates"][0]["ranking_is_lab_only"] is True
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_betrayal_inverse_remains_preview_only_and_blocked(tmp_path: Path) -> None:
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
                "true_paper_min_samples_required": 30,
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
        payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW, write=False)

    betrayal = payload["betrayal_inverse_lab_preview"]
    row = betrayal["capture_priorities"][0]
    assert betrayal["preview_only"] is True
    assert betrayal["betrayal_live_permission"] is False
    assert row["true_paper_outcomes_count"] == 12
    assert row["sample_progress_pct"] == 40.0
    assert row["betrayal_live_permission"] is False
    assert row["submit_allowed"] is False
    rendered = json.dumps(payload)
    assert "BETRAYAL_LIVE_ALLOWED" not in rendered


def test_direct_module_inspect_route_and_operator_script(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": "."}

    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.strategy_lab_variant_test_pack", "--help"],
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
            str(log_dir),
            "strategy-lab-variant-test-pack",
            "--no-write",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    script_result = subprocess.run(
        ["bash", "scripts/hammer_print_r305_strategy_lab_variant_pack.sh"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--log-dir" in help_result.stdout
    payload = json.loads(inspect_result.stdout)
    assert payload["event_type"] == EVENT_TYPE
    assert payload["submit_allowed"] is False
    assert "R305 STRATEGY LAB VARIANT TEST PACK" in script_result.stdout
    assert "TOP 10 VARIANT CANDIDATES" in script_result.stdout
    assert "SAFETY FLAGS" in script_result.stdout
    assert "secrets_shown: False" in script_result.stdout


def test_no_secrets_or_order_surfaces_are_called(tmp_path: Path) -> None:
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
        payload = build_strategy_lab_variant_test_pack(log_dir=log_dir, now=NOW, write=False)

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def _seed_strategy_status(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "qualified_candidate_watch": {
            "live_qualified_lanes": [
                _lane("44m", "long", "ladder_close_50_618", 58.57, 70, 0.0672),
                _lane("44m", "short", "ladder_close_50_618", 60.47, 86, 0.098),
                _lane("55m", "long", "ladder_close_50_618", 62.96, 54, 0.1042),
            ],
            "near_miss_incubator_lanes": [
                _lane("22m", "long", "ladder_close_50_618", 54.0, 35, 0.03),
                _lane("22m", "short", "ladder_close_50_618", 53.5, 32, 0.02),
                _lane("8m", "short", "ladder_close_50_618", 53.33, 30, 0.01),
            ],
            "paper_only_lanes": [
                _lane("13m", "long", "ladder_close_50_618", 47.27, 55, 0.01),
            ],
        },
        "recommendations": [
            _lane("44m", "short", "ladder_382_50_618", 67.74, 62, 0.0963),
            _lane("44m", "short", "ladder_22_44_22", 66.04, 53, 0.068),
            _lane("44m", "long", "ladder_382_50_618", 62.30, 61, 0.0647),
            _lane("88m", "long", "ladder_382_50_618", 57.14, 42, 0.0613),
            _lane("55m", "long", "market_close", 60.0, 55, 0.0574),
            _lane("44m", "long", "ladder_22_44_22", 56.25, 48, 0.0545),
        ],
    }
    with (log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _lane(timeframe: str, direction: str, entry_mode: str, win_rate_pct: float, sample_count: int, avg_pnl_pct: float) -> dict[str, object]:
    return {
        "strategy_key": f"BTCUSDT|{timeframe}|{direction}|{entry_mode}",
        "lane_key": f"BTCUSDT|{timeframe}|{direction}|{entry_mode}",
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "total_pnl_pct": round(avg_pnl_pct * sample_count, 4),
    }
