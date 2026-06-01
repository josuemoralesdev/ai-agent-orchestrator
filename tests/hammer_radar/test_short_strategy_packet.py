from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.short_strategy_packet import (
    CONFIRM_SHORT_STRATEGY_PACKET_RECORDING_PHRASE,
    DEFAULT_TARGET_LANE_KEY,
    LEDGER_FILENAME,
    PAPER_ONLY_COLLECT_MORE_EVIDENCE,
    SHORT_STRATEGY_PACKET_READY,
    SHORT_STRATEGY_PACKET_RECORDED,
    SHORT_STRATEGY_PACKET_REJECTED,
    build_short_strategy_packet,
    load_short_strategy_packet_records,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"


def test_preview_writes_no_packet(tmp_path: Path) -> None:
    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == SHORT_STRATEGY_PACKET_READY
    assert payload["packet_recorded"] is False
    assert payload["packet_id"] is None
    assert payload["record_packet_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        record_packet=True,
        confirm_short_strategy_packet="wrong",
        now=NOW,
    )

    assert payload["status"] == SHORT_STRATEGY_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_short_strategy_packet_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_packet_only(tmp_path: Path) -> None:
    config_path = _write_expanded_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")

    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        record_packet=True,
        confirm_short_strategy_packet=CONFIRM_SHORT_STRATEGY_PACKET_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_short_strategy_packet_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == SHORT_STRATEGY_PACKET_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SHORT_STRATEGY_PACKET"
    assert records[0]["safety"]["order_placed"] is False
    assert config_path.read_text(encoding="utf-8") == before


def test_default_target_is_8m_short_and_mode_is_paper(tmp_path: Path) -> None:
    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["target_family"]["lane_key"] == DEFAULT_TARGET_LANE_KEY
    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert payload["target_family"]["symbol"] == "BTCUSDT"
    assert payload["target_family"]["timeframe"] == "8m"
    assert payload["target_family"]["direction"] == "short"
    assert payload["target_family"]["entry_mode"] == "ladder_close_50_618"
    assert payload["target_family"]["current_mode"] == "paper"


def test_golden_pocket_interpretation_thresholds_and_insufficient_evidence_block_tiny_live(tmp_path: Path) -> None:
    _write_outcome(tmp_path / "logs", LANE_8M_SHORT, 0, pnl_pct=0.2)
    _write_signal(tmp_path / "logs", "BTCUSDT", "8m", "short", NOW - timedelta(seconds=5))

    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["short_strategy_interpretation"]["golden_pocket_role"] == "resistance/retrace zone"
    assert payload["thresholds_for_future_review"]["min_paper_outcomes"] == 30
    assert payload["thresholds_for_future_review"]["min_fresh_candidates"] == 10
    assert payload["thresholds_for_future_review"]["preferred_win_rate_pct"] == 52
    assert payload["thresholds_for_future_review"]["requires_operator_approval"] is True
    assert payload["readiness"] == PAPER_ONLY_COLLECT_MORE_EVIDENCE
    assert "paper outcome sample below 30" in payload["blockers_to_tiny_live"]
    assert "fresh short candidate sample below 10" in payload["blockers_to_tiny_live"]
    assert "short lane has no tiny_live authorization" in payload["blockers_to_tiny_live"]


def test_safe_commands_emit_no_lane_mode_apply_or_live_submit_commands(tmp_path: Path) -> None:
    payload = build_short_strategy_packet(
        log_dir=tmp_path / "logs",
        config_path=_write_expanded_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "short-strategy-packet" in joined
    assert "full-spectrum-betrayal-short-review" in joined
    assert "promotion-candidate-audit" in joined
    assert "expanded-paper-watch" in joined
    assert "live-connector-submit" not in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined
    assert "set short lane tiny_live" in payload["do_not_run_yet"]
    assert "set new lane tiny_live" in payload["do_not_run_yet"]


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
        payload = build_short_strategy_packet(
            log_dir=tmp_path / "logs",
            config_path=config_path,
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
            "short-strategy-packet",
            "--latest-outcomes",
            "10",
            "--latest-signals",
            "20",
            "--latest-betrayal",
            "10",
            "--latest-watch-records",
            "5",
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
    assert "target_family" in payload
    assert "short_strategy_interpretation" in payload
    assert "short-strategy-packet" in help_result.stdout


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
        "freshness_seconds": 60,
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


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
