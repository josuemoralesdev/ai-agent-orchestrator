from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_regime_miro_recheck import (
    BETRAYAL_EVENT_DIRECTION_SPLIT_STILL_REQUIRED,
    BETRAYAL_MIRO_PENDING_OR_BLOCKED,
    BETRAYAL_REGIME_MIRO_RECHECK_RECORDED,
    BETRAYAL_REGIME_MIRO_RECHECK_REJECTED,
    CONFIRM_BETRAYAL_REGIME_MIRO_RECHECK_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_regime_miro_recheck,
    load_betrayal_regime_miro_recheck_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_regime_miro_recheck(log_dir=log_dir, now=NOW)

    assert payload["record_recheck_requested"] is False
    assert payload["recheck_recorded"] is False
    assert payload["recheck_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_regime_miro_recheck(
        log_dir=log_dir,
        record_recheck=True,
        confirm_betrayal_regime_miro_recheck="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_REGIME_MIRO_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert load_betrayal_regime_miro_recheck_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_recheck_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_regime_miro_recheck(
        log_dir=log_dir,
        record_recheck=True,
        confirm_betrayal_regime_miro_recheck=CONFIRM_BETRAYAL_REGIME_MIRO_RECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_regime_miro_recheck_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_REGIME_MIRO_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_REGIME_MIRO_RECHECK"
    assert before_env == dict(os.environ)


def test_includes_222m_88m_55m_candidates_and_reuses_tracker_status(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_regime_miro_recheck(log_dir=log_dir, now=NOW)
    rows = {row["candidate"]: row for row in payload["betrayal_regime_miro_candidate_rows"]}

    assert set(rows) == {"222m aggregate", "88m aggregate", "55m aggregate"}
    assert rows["88m aggregate"]["context_score"] == 47.56
    assert rows["222m aggregate"]["resolved_true_inverse_samples"] == 15
    for row in rows.values():
        assert row["event_tracker_status"] == "BETRAYAL_EVENT_DIRECTION_SPLIT_REQUIRED"
        assert row["direction_split_resolved"] is False


def test_reports_miro_pending_and_regime_preview_when_no_gate_ledgers_exist(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_regime_miro_recheck(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["markov_regime_gate_found"] is False
    assert payload["input_summary"]["miro_fish_gate_found"] is False
    assert payload["betrayal_regime_context"]["222m"]["regime_source"] in {"local_preview", "missing"}
    assert payload["betrayal_miro_fish_context"]["222m"]["miro_status"] == BETRAYAL_MIRO_PENDING_OR_BLOCKED
    assert payload["betrayal_regime_miro_gap_report"]["miro_fish_missing_or_pending"] is True
    assert payload["betrayal_regime_miro_gap_report"]["regime_gate_missing_or_pending"] in {True, False}


def test_does_not_live_authorize_or_promote_betrayal(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_regime_miro_recheck(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert payload["regime_miro_status"] == BETRAYAL_EVENT_DIRECTION_SPLIT_STILL_REQUIRED
    for row in payload["betrayal_regime_miro_candidate_rows"]:
        assert row["live_ready"] is False
        assert row["promotion_allowed"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_no_env_config_destructive_network_binance_or_live_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_regime_miro_recheck(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "betrayal-regime-miro-recheck",
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
    assert "betrayal_regime_miro_candidate_rows" in payload
    assert "betrayal-regime-miro-recheck" in help_result.stdout


def _write_stack(log_dir: Path) -> None:
    _append_json(
        log_dir / "betrayal_event_tracker.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "event_tracker_status": "BETRAYAL_EVENT_DIRECTION_SPLIT_REQUIRED",
            "event_tracker_preview": {
                "aggregate_context_only_events": 3,
                "direction_specific_events": 0,
            },
            "event_tracker_gap_report": {
                "direction_split_missing": True,
            },
        },
    )
    _append_json(
        log_dir / "betrayal_paper_matrix_context.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_context_rows": [
                _matrix_row("88m", 47.56, 32, 14),
                _matrix_row("222m", 36.75, 15, 5),
                _matrix_row("55m", 28.75, 26, 26),
            ],
        },
    )
    _append_json(
        log_dir / "betrayal_true_inverse_refresh.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "candidate_true_inverse_summary": {
                "222m": _true_inverse("BETRAYAL_PRIMARY_CANDIDATE", 15, 5),
                "88m": _true_inverse("BETRAYAL_WATCHLIST", 32, 14),
                "55m": _true_inverse("BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY", 26, 26),
            },
        },
    )
    _write_candles(log_dir / "candle_archive" / "BTCUSDT_222m.ndjson", start=100.0, step=-0.3, count=20)
    _write_candles(log_dir / "candle_archive" / "BTCUSDT_88m.ndjson", start=100.0, step=0.0, count=20)
    _write_candles(log_dir / "candle_archive" / "BTCUSDT_55m.ndjson", start=100.0, step=0.2, count=20)


def _matrix_row(timeframe: str, score: float, resolved: int, unresolved: int) -> dict[str, object]:
    return {
        "candidate": f"{timeframe} aggregate",
        "timeframe": timeframe,
        "context_score": score,
        "resolved_true_inverse_samples": resolved,
        "unresolved_shadow_samples": unresolved,
        "risk_warnings": ["aggregate_direction_only", "paper_context_only"],
        "paper_only": True,
        "live_ready": False,
        "promotion_allowed": False,
    }


def _true_inverse(label: str, resolved: int, unresolved: int) -> dict[str, object]:
    return {
        "label": label,
        "resolved_true_inverse_samples": resolved,
        "unresolved_shadow_samples": unresolved,
        "validation_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
        "live_ready": False,
        "promotion_allowed": False,
    }


def _write_candles(path: Path, *, start: float, step: float, count: int) -> None:
    for index in range(count):
        close = start + (index * step)
        _append_json(
            path,
            {
                "open_time": (NOW + timedelta(minutes=index)).isoformat(),
                "open": close - 0.1,
                "high": close + 0.4,
                "low": close - 0.4,
                "close": close,
            },
        )


def _append_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
