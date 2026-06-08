import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.capture_priority_rebalance import (
    BETRAYAL_SHADOW_PRIORITY,
    CAPTURE_PRIORITY_REBALANCE_RECORDED,
    CAPTURE_PRIORITY_REBALANCE_REJECTED,
    CONFIRM_CAPTURE_PRIORITY_REBALANCE_RECORDING_PHRASE,
    NEAR_THRESHOLD_ALTERNATE,
    OFFICIAL_PROTECTED_TINY_LIVE_PATH,
    TINY_SAMPLE_TRAP,
    build_capture_priority_rebalance,
    calculate_capture_priority_score,
    load_capture_priority_rebalance_records,
)

NOW = datetime(2026, 6, 8, 18, 30, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
LONG_8M = "BTCUSDT|8m|long|ladder_close_50_618"
TRAP = "BTCUSDT|13h|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_capture_priority_rebalance(log_dir=log_dir, now=NOW)

    assert payload["rebalance_recorded"] is False
    assert payload["record_rebalance_requested"] is False
    assert load_capture_priority_rebalance_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert payload["target_scope"]["official_tiny_live_lane_changed"] is False


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_capture_priority_rebalance(
        log_dir=log_dir,
        record_rebalance=True,
        confirm_capture_priority_rebalance="wrong",
        now=NOW,
    )

    assert payload["status"] == CAPTURE_PRIORITY_REBALANCE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["rebalance_recorded"] is False
    assert load_capture_priority_rebalance_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_rebalance_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    protected_paths = {
        "lane_controls": log_dir.parent / "configs" / "hammer_radar" / "lane_controls.json",
        "risk_contracts": log_dir.parent / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json",
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
    }
    for path in protected_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    before = {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()}

    payload = build_capture_priority_rebalance(
        log_dir=log_dir,
        record_rebalance=True,
        confirm_capture_priority_rebalance=CONFIRM_CAPTURE_PRIORITY_REBALANCE_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_capture_priority_rebalance_records(log_dir=log_dir, limit=0)
    assert payload["status"] == CAPTURE_PRIORITY_REBALANCE_RECORDED
    assert payload["rebalance_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CAPTURE_PRIORITY_REBALANCE"
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()} == before
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["paper_outcome_ledger_rewritten"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_official_lane_remains_unchanged_and_highest_priority(tmp_path: Path) -> None:
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)
    first = payload["capture_priority_rows"][0]

    assert first["lane_key"] == OFFICIAL
    assert first["priority_group"] == OFFICIAL_PROTECTED_TINY_LIVE_PATH
    assert payload["official_protected_path_summary"]["fresh_capture_count"] == 8
    assert payload["official_protected_path_summary"]["threshold_distance_remaining"] == 2
    assert payload["official_protected_path_summary"]["recommended_action"] == "KEEP_AS_OFFICIAL_AND_WAIT_FOR_10_OF_10"
    assert payload["rebalance_plan"]["official_lane_unchanged"] is True


def test_8m_long_can_be_near_threshold_alternate_without_promotion(tmp_path: Path) -> None:
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)
    rows = {row["lane_key"]: row for row in payload["capture_priority_rows"]}

    assert rows[LONG_8M]["priority_group"] == NEAR_THRESHOLD_ALTERNATE
    assert rows[LONG_8M]["recommended_paper_action"] == "WATCH_CLOSELY"
    assert rows[LONG_8M]["unique_capture_count"] == 6
    assert rows[LONG_8M]["threshold_distance_remaining"] == 4
    assert rows[LONG_8M]["promotion_allowed"] is False
    assert rows[LONG_8M]["live_authorized"] is False
    assert payload["rebalance_plan"]["live_readiness_implied"] is False


def test_betrayal_context_is_preserved_when_available(tmp_path: Path) -> None:
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)
    betrayal_rows = [row for row in payload["capture_priority_rows"] if row["priority_group"] == BETRAYAL_SHADOW_PRIORITY]

    assert payload["target_scope"]["betrayal_shadow_preserved"] is True
    assert payload["betrayal_shadow_context"]["preserved"] is True
    assert payload["betrayal_shadow_context"]["status"] == "CONTEXT_ONLY"
    assert any("222m" in row["lane_key"] for row in betrayal_rows)
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_tiny_sample_traps_are_separated_from_real_candidates(tmp_path: Path) -> None:
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)
    rows = {row["lane_key"]: row for row in payload["capture_priority_rows"]}

    assert rows[TRAP]["priority_group"] == TINY_SAMPLE_TRAP
    assert rows[TRAP]["recommended_paper_action"] == "RESEARCH_ONLY"
    assert payload["capture_priority_gap_report"]["tiny_sample_trap_count"] >= 1


def test_priority_score_deterministic() -> None:
    row = {
        "priority_group": NEAR_THRESHOLD_ALTERNATE,
        "combined_watch_score": 58.44,
        "unique_capture_count": 6,
        "known_outcome_count": 302,
        "win_rate_pct": 71.85,
    }

    assert calculate_capture_priority_score(row) == calculate_capture_priority_score(row)


def test_priority_rank_does_not_imply_live_readiness_or_lane_promotion(tmp_path: Path) -> None:
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert all(row["paper_only"] is True for row in payload["capture_priority_rows"])
    assert all(row["live_authorized"] is False for row in payload["capture_priority_rows"])
    assert all(row["promotion_allowed"] is False for row in payload["capture_priority_rows"])
    assert payload["rebalance_plan"]["runtime_config_change_required"] is False
    assert payload["rebalance_plan"]["live_readiness_implied"] is False
    assert payload["safety"]["lane_promoted"] is False
    assert payload["safety"]["alternate_lane_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False


def test_no_fisherman_scheduler_env_config_or_destructive_mutation(tmp_path: Path) -> None:
    before_env = dict(os.environ)
    payload = build_capture_priority_rebalance(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    assert dict(os.environ) == before_env
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "registry_config_written",
        "scoring_config_written",
        "matrix_config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "fisherman_config_written",
        "scheduler_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "paper_outcome_ledger_rewritten",
    ):
        assert safety[key] is False


def test_no_binance_network_order_live_transfer_or_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_capture_priority_rebalance(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key in (
        "network_allowed",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "live_authorization_created",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "capture-priority-rebalance",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["rebalance_recorded"] is False


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    rows = [
        _enriched_row(OFFICIAL, "short", "8m", 8, 2, 292, 72.95, 61.04, "STRONG"),
        _enriched_row(LONG_8M, "long", "8m", 6, 4, 302, 71.85, 58.44, "STRONG"),
        _enriched_row("BTCUSDT|4m|short|ladder_close_50_618", "short", "4m", 4, 6, 635, 66.30, 49.78, "STRONG"),
        _enriched_row(TRAP, "short", "13H", 1, 9, 4, 100.0, 42.0, "VERY_STRONG"),
        _enriched_row("BTCUSDT|88m|long|entry_unknown", "long", "88m", 0, 10, 0, None, 0.0, "UNKNOWN"),
    ]
    _append(
        log_dir / "lane_outcome_enrichment.ndjson",
        {
            "event_type": "LANE_OUTCOME_ENRICHMENT",
            "enrichment_id": "r232_fixture",
            "generated_at": NOW.isoformat(),
            "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
            "input_summary": {"scoreboard_found": True, "tiny_live_capture_sync_found": True},
            "official_tiny_live_lane_status": {
                "lane_key": OFFICIAL,
                "fresh_capture_count": 8,
                "required_fresh_capture_count": 10,
                "threshold_met": False,
                "threshold_distance_remaining": 2,
                "watcher_likely_running": True,
                "watcher_stale": False,
                "fisherman_status": "FISHERMAN_RUNNING_RECENT",
            },
            "enriched_lane_rows": rows,
            "safety": {"config_written": False, "order_placed": False},
        },
    )
    _append(
        log_dir / "full_spectrum_lane_scoreboard.ndjson",
        {
            "event_type": "FULL_SPECTRUM_LANE_SCOREBOARD",
            "scoreboard_id": "r231_fixture",
            "generated_at": NOW.isoformat(),
            "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
            "official_tiny_live_lane_status": {
                "lane_key": OFFICIAL,
                "fresh_capture_count": 8,
                "required_fresh_capture_count": 10,
                "threshold_met": False,
                "threshold_distance_remaining": 2,
                "watcher_likely_running": True,
                "watcher_stale": False,
                "fisherman_status": "FISHERMAN_RUNNING_RECENT",
            },
            "lane_scoreboard_rows": rows,
        },
    )
    _append(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "capture_count": {
                "fresh_capture_count": 8,
                "required_fresh_capture_count": 10,
                "threshold_met": False,
            },
            "watcher_status": {"watcher_likely_running": True, "watcher_stale": False},
            "threshold_status": "CAPTURE_THRESHOLD_NOT_MET",
        },
    )
    _append(
        log_dir / "weekend_paper_fisherman_supervisor.ndjson",
        {
            "betrayal_watch_summary": {
                "betrayal_context_included": True,
                "latest_222m_capture_lane": "BTCUSDT|222m|long|ladder_close_50_618",
                "primary_betrayal_candidate": "222m aggregate",
                "primary_betrayal_naive_inverse_win_rate_pct": 87.5,
                "watchlist_betrayal_candidate": "88m aggregate",
                "watchlist_betrayal_naive_inverse_win_rate_pct": 63.33,
            },
            "fisherman_health": {"fisherman_status": "FISHERMAN_RUNNING_RECENT"},
        },
    )
    _append(
        log_dir / "betrayal_direction_completion.ndjson",
        {
            "direction_completed_rows_preview": [
                {
                    "candidate": "222m aggregate",
                    "symbol": "BTCUSDT",
                    "timeframe": "222m",
                    "entry_mode": "ladder_close_50_618",
                    "inverse_direction": "long",
                    "emitted_direction": "long",
                    "lane_key_preview": "BTCUSDT|222m|long|ladder_close_50_618",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                    "why": "fixture betrayal shadow context",
                }
            ]
        },
    )
    _append(
        log_dir / "betrayal_shadow_outcomes.ndjson",
        {
            "symbol": "BTCUSDT",
            "timeframe": "88m",
            "shadow_direction": "short",
            "betrayal_tier": "STRONG_BETRAYAL_WATCH",
            "shadow_only": True,
            "order_placed": False,
        },
    )
    return log_dir


def _enriched_row(
    lane_key: str,
    direction: str,
    timeframe: str,
    unique: int,
    distance: int,
    known: int,
    win_rate: float | None,
    combined: float,
    quality: str,
) -> dict[str, object]:
    return {
        "lane_key": lane_key,
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": lane_key.split("|")[-1],
        "unique_capture_count": unique,
        "threshold_distance_remaining": distance,
        "threshold_required_count": 10,
        "known_outcome_count": known,
        "win_rate_pct": win_rate,
        "combined_watch_score": combined,
        "outcome_quality_score": combined,
        "win_rate_quality_bucket": quality,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
