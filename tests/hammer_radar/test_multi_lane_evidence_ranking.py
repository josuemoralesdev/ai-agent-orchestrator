from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_evidence_ranking import (
    CONFIRM_MULTI_LANE_RANKING_RECORDING_PHRASE,
    EIGHT_M_SHORT_REMAINS_LEAD,
    KEEP_HARVESTING_INSUFFICIENT_EVIDENCE,
    LEDGER_FILENAME,
    MULTI_LANE_EVIDENCE_RANKING_RECORDED,
    MULTI_LANE_EVIDENCE_RANKING_REJECTED,
    build_multi_lane_evidence_ranking,
    load_multi_lane_evidence_ranking_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_4M_SHORT = "BTCUSDT|4m|short|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_multi_lane_evidence_ranking(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_ranking_requested"] is False
    assert payload["ranking_recorded"] is False
    assert payload["ranking_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_multi_lane_evidence_ranking(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_ranking=True,
        confirm_multi_lane_ranking="wrong",
        now=NOW,
    )

    assert payload["status"] == MULTI_LANE_EVIDENCE_RANKING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["ranking_recorded"] is False
    assert load_multi_lane_evidence_ranking_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_multi_lane_evidence_ranking(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        record_ranking=True,
        confirm_multi_lane_ranking=CONFIRM_MULTI_LANE_RANKING_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_multi_lane_evidence_ranking_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == MULTI_LANE_EVIDENCE_RANKING_RECORDED
    assert payload["ranking_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "MULTI_LANE_EVIDENCE_RANKING"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_8m_short_remains_lead_when_highest_fresh_capture_count(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {LANE_8M_SHORT: 3, LANE_4M_SHORT: 1})

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["ranked_lanes"][0]["lane_key"] == LANE_8M_SHORT
    assert payload["ranked_lanes"][0]["readiness"] == EIGHT_M_SHORT_REMAINS_LEAD
    assert payload["next_door_selection"]["selection_type"] == "KEEP_8M_SHORT"
    assert payload["current_lead"]["fresh_capture_count"] == 3


def test_new_lane_candidate_emerges_when_mocked_fresh_captures_exceed_8m_short(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {LANE_8M_SHORT: 3, LANE_4M_LONG: 11})

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["ranked_lanes"][0]["lane_key"] == LANE_4M_LONG
    assert payload["next_door_selection"]["selected_lane"] == LANE_4M_LONG
    assert payload["next_door_selection"]["selection_type"] == "NEW_LANE_CANDIDATE"
    assert payload["recommended_next_operator_move"] == "RUN_R182_SIGNAL_ORIGIN_REGISTRY"


def test_stale_count_alone_does_not_make_lane_ready(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {}, stale_by_lane={LANE_4M_SHORT: 250})

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    row = _row(payload, LANE_4M_SHORT)

    assert row["fresh_capture_count"] == 0
    assert row["fresh_threshold_met"] is False
    assert row["readiness"] == KEEP_HARVESTING_INSUFFICIENT_EVIDENCE
    assert "stale count alone is not readiness evidence" in " ".join(row["blockers"])


def test_tiny_live_observed_reference_does_not_auto_promote(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {}, observed_by_lane={LANE_13M_LONG: 40})

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    row = _row(payload, LANE_13M_LONG)

    assert row["mode"] == "tiny_live_observed_reference"
    assert row["reference_only"] is True
    assert "reference only" in " ".join(row["blockers"])
    assert payload["next_door_selection"]["selected_lane"] != LANE_13M_LONG


def test_ranking_includes_score_readiness_and_historical_performance(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {LANE_4M_LONG: 10})
    for index in range(3):
        _append_json(
            log_dir / "outcomes.ndjson",
            {
                "symbol": "BTCUSDT",
                "timeframe": "4m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "status": "filled",
                "pnl_pct": 0.2 if index < 2 else -0.1,
            },
        )

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    row = _row(payload, LANE_4M_LONG)

    assert isinstance(row["score"], int)
    assert row["readiness"]
    assert row["historical_win_rate_pct"] == 66.67
    assert row["paper_outcome_count"] == 3


def test_next_door_selection_works(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_harvest_record(log_dir, {LANE_8M_SHORT: 10})

    payload = build_multi_lane_evidence_ranking(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["next_door_selection"]["selected_lane"] == LANE_8M_SHORT
    assert payload["next_door_selection"]["selection_type"] == "KEEP_8M_SHORT"
    assert payload["next_door_selection"]["next_required_phase"] == "R177"


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_multi_lane_evidence_ranking(log_dir=tmp_path / "logs", config_path=config_path, now=NOW)

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    for key, value in safety.items():
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
            "multi-lane-evidence-ranking",
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
    assert "ranked_lanes" in payload
    assert "next_door_selection" in payload
    assert "multi-lane-evidence-ranking" in help_result.stdout


def _write_harvest_record(
    log_dir: Path,
    captured_by_lane: dict[str, int],
    *,
    stale_by_lane: dict[str, int] | None = None,
    observed_by_lane: dict[str, int] | None = None,
) -> None:
    captured = []
    fresh_by_lane = {}
    for lane_key, count in captured_by_lane.items():
        fresh_by_lane[lane_key] = count
        for index in range(count):
            captured.append({"lane_key": lane_key, "signal_id": f"{lane_key}-{index}"})
    _append_json(
        log_dir / "multi_lane_paper_harvester.ndjson",
        {
            "event_type": "MULTI_LANE_PAPER_CAPTURE_HARVESTER",
            "harvest_id": "harvest-1",
            "status": "MULTI_LANE_PAPER_HARVESTER_CAPTURED",
            "harvest_status": "CAPTURED_ONE_OR_MORE_LANES",
            "capture_summary": {
                "fresh_by_lane": fresh_by_lane,
                "stale_by_lane": stale_by_lane or {},
                "observed_tiny_live_by_lane": observed_by_lane or {},
                "captured_candidates": captured,
            },
            "captured_candidates": captured,
        },
    )


def _row(payload: dict[str, object], lane_key: str) -> dict[str, object]:
    return next(row for row in payload["ranked_lanes"] if row["lane_key"] == lane_key)


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
