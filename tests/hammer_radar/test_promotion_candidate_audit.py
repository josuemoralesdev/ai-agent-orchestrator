from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.promotion_candidate_audit import (
    CONFIRM_PROMOTION_CANDIDATE_AUDIT_RECORDING_PHRASE,
    DO_NOT_PROMOTE,
    LEDGER_FILENAME,
    NOT_ENOUGH_EVIDENCE,
    PROMOTION_CANDIDATE_AUDIT_READY,
    PROMOTION_CANDIDATE_AUDIT_RECORDED,
    PROMOTION_CANDIDATE_AUDIT_REJECTED,
    STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW,
    build_promotion_candidate_audit,
    load_promotion_candidate_audit_records,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_4M_SHORT = "BTCUSDT|4m|short|ladder_close_50_618"
LANE_8M_LONG = "BTCUSDT|8m|long|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_audit(tmp_path: Path) -> None:
    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )

    assert payload["status"] == PROMOTION_CANDIDATE_AUDIT_READY
    assert payload["audit_recorded"] is False
    assert payload["audit_id"] is None
    assert payload["record_audit_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        record_audit=True,
        confirm_promotion_audit="wrong",
        now=NOW,
    )

    assert payload["status"] == PROMOTION_CANDIDATE_AUDIT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["audit_recorded"] is False
    assert load_promotion_candidate_audit_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_audit_only(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        record_audit=True,
        confirm_promotion_audit=CONFIRM_PROMOTION_CANDIDATE_AUDIT_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_promotion_candidate_audit_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == PROMOTION_CANDIDATE_AUDIT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["audit_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PROMOTION_CANDIDATE_AUDIT"
    assert records[0]["safety"]["order_placed"] is False
    assert config_path.read_text(encoding="utf-8") == before


def test_paper_lanes_and_tiny_live_incumbents_included_as_reference_only(tmp_path: Path) -> None:
    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )
    families = payload["lane_families"]

    assert families[LANE_4M_LONG]["mode"] == "paper"
    assert families[LANE_4M_SHORT]["mode"] == "paper"
    assert families[LANE_13M_LONG]["mode"] == "tiny_live"
    assert families[LANE_44M_LONG]["mode"] == "tiny_live"
    assert payload["incumbent_tiny_live_review"]["review_only"] is True
    assert payload["incumbent_tiny_live_review"]["mode_changes_recommended"] is False


def test_short_lanes_remain_paper_only_and_require_future_short_review(tmp_path: Path) -> None:
    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        include_tiny_live_incumbents=True,
        now=NOW,
    )

    assert payload["lane_families"][LANE_4M_SHORT]["mode"] == "paper"
    assert payload["short_lane_review"]["shorts_seen"] is True
    assert payload["short_lane_review"]["shorts_remain_paper_only"] is True
    assert payload["short_lane_review"]["requires_future_short_strategy_review"] is True


def test_safe_commands_emit_no_live_or_lane_apply_commands(tmp_path: Path) -> None:
    payload = build_promotion_candidate_audit(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "expanded-paper-watch" in joined
    assert "promotion-candidate-audit" in joined
    assert "candidate-source-freshness-audit" in joined
    assert "live-connector-submit" not in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]


def test_ranking_handles_missing_outcome_fields(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_jsonl(log_dir / "outcomes.ndjson", {"symbol": "BTCUSDT", "timeframe": "4m", "direction": "long"})

    payload = build_promotion_candidate_audit(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )

    assert payload["status"] == PROMOTION_CANDIDATE_AUDIT_READY
    assert LANE_4M_LONG in payload["lane_families"]
    assert payload["lane_families"][LANE_4M_LONG]["readiness"] == NOT_ENOUGH_EVIDENCE


def test_ranking_identifies_insufficient_evidence(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_outcome(log_dir, LANE_4M_LONG, 0, pnl_pct=0.2)

    payload = build_promotion_candidate_audit(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )

    assert payload["lane_families"][LANE_4M_LONG]["performance"]["paper_outcome_count"] == 1
    assert payload["lane_families"][LANE_4M_LONG]["readiness"] == NOT_ENOUGH_EVIDENCE


def test_ranking_identifies_strong_paper_candidate_from_positive_samples(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(30):
        pnl = 0.2 if index < 20 else -0.05
        _write_outcome(log_dir, LANE_8M_LONG, index, pnl_pct=pnl)
    for index in range(10):
        _write_signal(log_dir, "BTCUSDT", "8m", "long", NOW - timedelta(seconds=index + 1))

    payload = build_promotion_candidate_audit(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )

    row = payload["lane_families"][LANE_8M_LONG]
    assert row["performance"]["paper_outcome_count"] == 30
    assert row["performance"]["win_rate_pct"] >= 52.0
    assert row["opportunity"]["fresh_candidate_count"] >= 10
    assert row["readiness"] == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW
    assert payload["ranked_candidates"][0]["lane_key"] == LANE_8M_LONG


def test_stop_dominated_candidate_does_not_promote(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(30):
        _write_outcome(log_dir, LANE_4M_LONG, index, pnl_pct=-0.1, stop_hit=index < 25)
    for index in range(10):
        _write_signal(log_dir, "BTCUSDT", "4m", "long", NOW - timedelta(seconds=index + 1))

    payload = build_promotion_candidate_audit(
        log_dir=log_dir,
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        include_paper_lanes=True,
        now=NOW,
    )

    assert payload["lane_families"][LANE_4M_LONG]["readiness"] == DO_NOT_PROMOTE


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
        payload = build_promotion_candidate_audit(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            include_paper_lanes=True,
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
            "promotion-candidate-audit",
            "--latest-outcomes",
            "10",
            "--latest-signals",
            "20",
            "--latest-watch-records",
            "5",
            "--include-paper-lanes",
            "--include-tiny-live-incumbents",
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
    assert "lane_families" in payload
    assert "ranked_candidates" in payload
    assert "promotion-candidate-audit" in help_result.stdout


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


def _lane(timeframe: str, direction: str, mode: str) -> dict:
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


def _write_outcome(log_dir: Path, lane_key: str, index: int, *, pnl_pct: float, stop_hit: bool = False) -> None:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    timestamp = NOW - timedelta(minutes=120 - index)
    _write_jsonl(
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
    _write_jsonl(
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


def _write_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
