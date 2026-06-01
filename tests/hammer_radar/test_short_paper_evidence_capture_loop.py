from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
    DEFAULT_LANE_KEY,
    HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME,
    SHORT_PAPER_CAPTURE_EXITED,
    SHORT_PAPER_CAPTURE_ITERATION_COMPLETED,
    SHORT_PAPER_CAPTURE_ITERATION_STARTED,
    SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD,
    SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED,
    SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT,
    SHORT_PAPER_EVIDENCE_CAPTURED,
    build_short_paper_evidence_capture_preview,
    build_short_paper_target_lane,
    evaluate_short_paper_candidate_window,
    load_short_paper_evidence_capture_records,
    run_short_paper_evidence_capture_loop,
    summarize_short_paper_evidence_capture_records,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def test_preview_writes_no_capture(tmp_path: Path) -> None:
    payload = build_short_paper_evidence_capture_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["watch_started"] is False
    assert payload["record_capture_requested"] is False
    assert payload["paper_evidence_captured"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_capture_loop(tmp_path: Path) -> None:
    payload = run_short_paper_evidence_capture_loop(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        run_capture_loop=True,
        record_capture=True,
        confirm_short_paper_capture="wrong",
        now=NOW,
    )

    assert payload["status"] == SHORT_PAPER_EVIDENCE_CAPTURE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["paper_evidence_captured"] is False
    assert load_short_paper_evidence_capture_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_capture_heartbeat_and_summary(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=5), signal_id="fresh-short")

    payload = run_short_paper_evidence_capture_loop(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        max_iterations=2,
        sleep_seconds=1,
        run_capture_loop=True,
        record_capture=True,
        confirm_short_paper_capture=CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
        now=NOW,
        sleep_fn=lambda _seconds: None,
    )

    records = load_short_paper_evidence_capture_records(log_dir=log_dir, limit=0)
    heartbeats = _read_ndjson(log_dir / HEARTBEAT_LEDGER_FILENAME)
    summary = summarize_short_paper_evidence_capture_records(records)

    assert payload["status"] == SHORT_PAPER_EVIDENCE_CAPTURED
    assert payload["paper_evidence_captured"] is True
    assert payload["captured_signal_id"] == "fresh-short"
    assert len(records) == 1
    assert summary["fresh_candidate_count_added"] == 1
    assert {row["status"] for row in heartbeats} >= {
        SHORT_PAPER_CAPTURE_ITERATION_STARTED,
        SHORT_PAPER_CAPTURE_EXITED,
    }


def test_default_target_lane_is_btcusdt_8m_short() -> None:
    target = build_short_paper_target_lane()

    assert target["lane_key"] == DEFAULT_LANE_KEY
    assert target["symbol"] == "BTCUSDT"
    assert target["timeframe"] == "8m"
    assert target["direction"] == "short"
    assert target["entry_mode"] == "ladder_close_50_618"


def test_target_lane_mode_must_be_paper(tmp_path: Path) -> None:
    target = build_short_paper_target_lane(config_path=_write_config(tmp_path / "lane_controls.json", short_mode="tiny_live"))
    payload = build_short_paper_evidence_capture_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls_2.json", short_mode="tiny_live"),
        now=NOW,
    )

    assert target["mode"] == "tiny_live"
    assert payload["target_lane"]["mode"] == "tiny_live"
    assert payload["evidence_summary"]["short_lane_remains_paper"] is False


def test_stale_short_candidate_is_not_captured(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=600), signal_id="stale-short")

    window = evaluate_short_paper_candidate_window(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert window["matching_lane_count"] == 1
    assert window["fresh_matching_count"] == 0
    assert window["stale_matching_count"] == 1
    assert window["capture_allowed_count"] == 0


def test_fresh_short_candidate_can_be_captured_from_mocked_recent_signals(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "8m", "short", NOW - timedelta(seconds=10), signal_id="fresh-short")

    window = evaluate_short_paper_candidate_window(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert window["fresh_matching_count"] == 1
    assert window["tradable_matching_count"] == 1
    assert window["capture_allowed_count"] == 1
    assert window["capturable_candidates"][0]["signal_id"] == "fresh-short"


def test_long_candidate_is_ignored(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "8m", "long", NOW - timedelta(seconds=10))

    window = evaluate_short_paper_candidate_window(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert window["matching_lane_count"] == 0
    assert window["capture_allowed_count"] == 0
    assert any(row["blocker"] == "direction mismatch" for row in window["top_blockers"])


def test_wrong_timeframe_candidate_is_ignored(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_signal(log_dir, "BTCUSDT", "13m", "short", NOW - timedelta(seconds=10))

    window = evaluate_short_paper_candidate_window(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert window["matching_lane_count"] == 0
    assert window["capture_allowed_count"] == 0
    assert any(row["blocker"] == "timeframe mismatch" for row in window["top_blockers"])


def test_heartbeat_writes_start_completion_exit(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = run_short_paper_evidence_capture_loop(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        max_iterations=1,
        sleep_seconds=1,
        run_capture_loop=True,
        record_capture=True,
        confirm_short_paper_capture=CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
        now=NOW,
    )
    statuses = [row["status"] for row in _read_ndjson(log_dir / HEARTBEAT_LEDGER_FILENAME)]

    assert payload["iterations_completed"] == 1
    assert statuses == [
        SHORT_PAPER_CAPTURE_ITERATION_STARTED,
        SHORT_PAPER_CAPTURE_ITERATION_COMPLETED,
        SHORT_PAPER_CAPTURE_EXITED,
    ]


def test_performance_guard_triggers_timeout_status_when_mocked_evaluator_is_slow(tmp_path: Path) -> None:
    def slow_window(**kwargs: object) -> dict[str, object]:
        time.sleep(2)
        return {
            "signals_checked": 0,
            "matching_lane_count": 0,
            "fresh_matching_count": 0,
            "stale_matching_count": 0,
            "tradable_matching_count": 0,
            "top_blockers": [],
            "safety": {},
        }

    with patch(
        "src.app.hammer_radar.operator.short_paper_evidence_capture_loop.evaluate_short_paper_candidate_window",
        side_effect=slow_window,
    ):
        payload = run_short_paper_evidence_capture_loop(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            max_iterations=1,
            iteration_timeout_seconds=1,
            run_capture_loop=True,
            record_capture=True,
            confirm_short_paper_capture=CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
            now=NOW,
        )

    statuses = [row["status"] for row in _read_ndjson(tmp_path / "logs" / HEARTBEAT_LEDGER_FILENAME)]
    assert payload["status"] == SHORT_PAPER_EVIDENCE_CAPTURE_TIMEOUT
    assert SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD in statuses


def test_no_lane_mode_apply_commands_emitted(tmp_path: Path) -> None:
    payload = build_short_paper_evidence_capture_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "short-paper-evidence-capture-loop" in joined
    assert "short-strategy-packet" in joined
    assert "full-spectrum-betrayal-short-review" in joined
    assert "lane-control-command" not in joined
    assert "--apply" not in joined


def test_no_live_commands_emitted(tmp_path: Path) -> None:
    payload = build_short_paper_evidence_capture_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    joined = "\n".join(payload["safe_commands"]).lower()

    assert "live-connector-submit" not in joined
    assert "order endpoint" not in joined
    assert "global live flag arming" not in joined
    assert "kill switch disable" not in joined


def test_safety_flags_clean(tmp_path: Path) -> None:
    payload = build_short_paper_evidence_capture_preview(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_order_payload_network_env_config_or_global_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    config_path = _write_config(tmp_path / "lane_controls.json")
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
        payload = run_short_paper_evidence_capture_loop(
            log_dir=tmp_path / "logs",
            config_path=config_path,
            max_iterations=1,
            sleep_seconds=1,
            run_capture_loop=True,
            record_capture=True,
            confirm_short_paper_capture=CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
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
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["global_live_flags_changed"] is False


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "short-paper-evidence-capture-loop",
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
    assert payload["target_lane"]["lane_key"] == DEFAULT_LANE_KEY
    assert "candidate_window" in payload
    assert "short-paper-evidence-capture-loop" in help_result.stdout


def _write_config(path: Path, *, short_mode: str = "paper") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "notes": ["test config"],
                "lanes": [
                    _lane("13m", "long", "tiny_live", 120),
                    _lane("44m", "long", "tiny_live", 300),
                    _lane("8m", "short", short_mode, 60),
                    _lane("13m", "short", "paper", 120),
                    _lane("8m", "long", "paper", 60),
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _lane(timeframe: str, direction: str, mode: str, freshness_seconds: int) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": mode,
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.15,
        "freshness_seconds": freshness_seconds,
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
    signal_id: str | None = None,
) -> None:
    _append(
        log_dir / "signals.ndjson",
        {
            "signal_id": signal_id or f"{symbol}-{timeframe}-{direction}-{timestamp.isoformat()}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "timestamp": timestamp.isoformat(),
        },
    )


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _read_ndjson(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
