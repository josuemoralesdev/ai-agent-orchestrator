from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.full_spectrum_betrayal_short_review import (
    CONFIRM_FULL_SPECTRUM_REVIEW_RECORDING_PHRASE,
    FULL_SPECTRUM_BETRAYAL_REVIEW_READY,
    FULL_SPECTRUM_BETRAYAL_REVIEW_RECORDED,
    FULL_SPECTRUM_BETRAYAL_REVIEW_REJECTED,
    LEDGER_FILENAME,
    NOT_ENOUGH_EVIDENCE,
    SHORT_STRATEGY_REVIEW_REQUIRED,
    build_betrayal_inverse_matrix,
    build_full_spectrum_betrayal_short_review,
    load_full_spectrum_betrayal_review_records,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        include_betrayal_inverse=True,
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_BETRAYAL_REVIEW_READY
    assert payload["audit_recorded"] is False
    assert payload["audit_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        record_review=True,
        confirm_full_spectrum_review="wrong",
        now=NOW,
    )

    assert payload["status"] == FULL_SPECTRUM_BETRAYAL_REVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["audit_recorded"] is False
    assert load_full_spectrum_betrayal_review_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_review_only(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        include_betrayal_inverse=True,
        record_review=True,
        confirm_full_spectrum_review=CONFIRM_FULL_SPECTRUM_REVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_full_spectrum_betrayal_review_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == FULL_SPECTRUM_BETRAYAL_REVIEW_RECORDED
    assert payload["audit_recorded"] is True
    assert payload["confirmation_valid"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "FULL_SPECTRUM_BETRAYAL_SHORT_REVIEW"
    assert config_path.read_text(encoding="utf-8") == before


def test_full_spectrum_includes_long_short_and_timeframes(tmp_path: Path) -> None:
    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )

    assert "long" in payload["scope"]["directions"]
    assert "short" in payload["scope"]["directions"]
    for timeframe in ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "4h", "444m", "666m", "888m"):
        assert timeframe in payload["scope"]["timeframes"]
        assert f"{timeframe}|long" in payload["direction_timeframe_matrix"]
        assert f"{timeframe}|short" in payload["direction_timeframe_matrix"]


def test_short_strategy_review_marks_golden_pocket_as_resistance_and_paper_only(tmp_path: Path) -> None:
    for index in range(30):
        _write_outcome(tmp_path / "logs", LANE_8M_SHORT, index, pnl_pct=0.25 if index < 22 else -0.05)
    for index in range(12):
        _write_signal(tmp_path / "logs", "BTCUSDT", "8m", "short", NOW - timedelta(seconds=index + 1))

    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )

    review = payload["short_strategy_review"]
    assert review["shorts_seen"] is True
    assert review["short_golden_pocket_interpretation"] == "resistance/retrace zone"
    assert review["shorts_remain_paper_only"] is True
    assert review["requires_future_short_strategy_review"] is True
    assert payload["candidate_rankings"][0]["lane_family"] == LANE_8M_SHORT
    assert payload["candidate_rankings"][0]["readiness"] == SHORT_STRATEGY_REVIEW_REQUIRED
    assert payload["next_tiny_live_candidate_door"]["recommendation_type"] == "SHORT_STRATEGY_REVIEW"
    assert payload["next_tiny_live_candidate_door"]["config_change_allowed_now"] is False


def test_no_lane_mode_apply_or_live_commands_emitted(tmp_path: Path) -> None:
    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "expanded-paper-watch" in joined
    assert "promotion-candidate-audit" in joined
    assert "full-spectrum-betrayal-short-review" in joined
    assert "candidate-source-freshness-audit" in joined
    assert "live-connector-submit" not in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]


def test_betrayal_inverse_matrix_handles_available_mocked_records() -> None:
    matrix = build_betrayal_inverse_matrix(
        lanes=[_lane("8m", "short", "paper")],
        betrayal_records=[
            _betrayal_record("8m", "long", "short", "SHADOW_WIN", 0.3, wins=0, losses=1),
            _betrayal_record("8m", "long", "short", "SHADOW_LOSS", -0.1, wins=1, losses=0),
            _betrayal_record("8m", "long", "short", "SHADOW_WIN", 0.2, wins=0, losses=1),
        ],
    )

    assert matrix["8m|short"]["sample_count"] == 3
    assert matrix["8m|short"]["inverse_win_rate_pct"] == 66.67
    assert matrix["8m|short"]["inverse_avg_pnl_pct"] == 0.1333
    assert matrix["8m|short"]["confidence"] == "LOW"


def test_betrayal_inverse_matrix_handles_missing_records_honestly() -> None:
    matrix = build_betrayal_inverse_matrix(lanes=[_lane("8m", "short", "paper")], betrayal_records=[])

    assert matrix["8m|short"]["sample_count"] == 0
    assert matrix["8m|short"]["inverse_win_rate_pct"] is None
    assert matrix["8m|short"]["inverse_avg_pnl_pct"] is None
    assert matrix["8m|short"]["confidence"] == "UNKNOWN"


def test_candidate_ranking_does_not_score_high_on_signal_count_alone(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(100):
        _write_signal(log_dir, "BTCUSDT", "4m", "long", NOW - timedelta(seconds=index + 1))

    payload = build_full_spectrum_betrayal_short_review(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )

    row = next(item for item in payload["candidate_rankings"] if item["lane_family"] == LANE_4M_LONG)
    assert row["score"] < 60
    assert row["readiness"] == NOT_ENOUGH_EVIDENCE


def test_low_sample_betrayal_advantage_does_not_auto_promote(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(2):
        _write_betrayal(log_dir, "8m", "long", "short", "SHADOW_WIN", 0.4, wins=0, losses=1, index=index)

    payload = build_full_spectrum_betrayal_short_review(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_betrayal_inverse=True,
        now=NOW,
    )

    row = next(item for item in payload["candidate_rankings"] if item["lane_family"] == LANE_8M_SHORT)
    assert payload["betrayal_inverse_matrix"]["8m|short"]["confidence"] == "LOW"
    assert row["score"] < 75
    assert row["readiness"] == NOT_ENOUGH_EVIDENCE


def test_incumbent_tiny_live_lanes_reviewed_but_not_changed(tmp_path: Path) -> None:
    payload = build_full_spectrum_betrayal_short_review(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )

    review = payload["incumbent_tiny_live_review"]
    assert review["review_only"] is True
    assert review["mode_changes_recommended"] is False
    assert LANE_13M_LONG in review["incumbent_lane_keys"]
    assert LANE_44M_LONG in review["incumbent_lane_keys"]


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
        payload = build_full_spectrum_betrayal_short_review(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            include_paper_lanes=True,
            include_tiny_live_incumbents=True,
            include_betrayal_inverse=True,
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
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
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
            "full-spectrum-betrayal-short-review",
            "--latest-outcomes",
            "10",
            "--latest-signals",
            "20",
            "--latest-betrayal",
            "10",
            "--latest-watch-records",
            "5",
            "--include-paper-lanes",
            "--include-tiny-live-incumbents",
            "--include-betrayal-inverse",
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
    assert "direction_timeframe_matrix" in payload
    assert "short_strategy_review" in payload
    assert "full-spectrum-betrayal-short-review" in help_result.stdout


def _write_expanded_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("13m", "long", "tiny_live"),
        _lane("44m", "long", "tiny_live"),
        _lane("8m", "long", "paper"),
        _lane("4m", "long", "paper"),
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
        "freshness_seconds": 120,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }


def _write_outcome(log_dir: Path, lane_key: str, index: int, *, pnl_pct: float, stop_hit: bool = False) -> None:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    timestamp = NOW - timedelta(minutes=120 - index)
    _append(
        log_dir / "outcomes.ndjson",
        {
            "signal_id": f"{lane_key}|{index}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "timestamp": timestamp.isoformat(),
            "evaluated_at": (timestamp + timedelta(minutes=1)).isoformat(),
            "fill_status": "filled",
            "outcome": "win" if pnl_pct > 0 else "stop" if stop_hit else "loss",
            "pnl_pct": pnl_pct,
            "stop_hit": stop_hit,
        },
    )


def _write_signal(log_dir: Path, symbol: str, timeframe: str, direction: str, timestamp: datetime) -> None:
    _append(
        log_dir / "signals.ndjson",
        {
            "signal_id": f"{symbol}|{timeframe}|{direction}|{timestamp.isoformat()}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": "ladder_close_50_618",
            "timestamp": timestamp.isoformat(),
        },
    )


def _write_betrayal(
    log_dir: Path,
    timeframe: str,
    original_direction: str,
    shadow_direction: str,
    status: str,
    pnl_pct: float,
    *,
    wins: int,
    losses: int,
    index: int,
) -> None:
    _append(log_dir / "betrayal_shadow_outcomes.ndjson", _betrayal_record(timeframe, original_direction, shadow_direction, status, pnl_pct, wins=wins, losses=losses, index=index))


def _betrayal_record(
    timeframe: str,
    original_direction: str,
    shadow_direction: str,
    status: str,
    pnl_pct: float,
    *,
    wins: int,
    losses: int,
    index: int = 0,
) -> dict[str, object]:
    return {
        "shadow_outcome_id": f"{timeframe}-{shadow_direction}-{index}",
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "original_direction": original_direction,
        "shadow_direction": shadow_direction,
        "shadow_status": status,
        "shadow_pnl_pct": pnl_pct,
        "original_outcome_summary": {"wins": wins, "losses": losses},
    }


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
