from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.keter_signal_origin_scoring import (
    CONFIRM_KETER_SIGNAL_ORIGIN_SCORING_RECORDING_PHRASE,
    KETER_SIGNAL_ORIGIN_SCORING_RECORDED,
    KETER_SIGNAL_ORIGIN_SCORING_REJECTED,
    LEDGER_FILENAME,
    build_keter_signal_origin_scoring,
    load_keter_signal_origin_scoring_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_scoring_requested"] is False
    assert payload["scoring_recorded"] is False
    assert payload["scoring_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(
        log_dir=tmp_path / "logs",
        record_scoring=True,
        confirm_keter_origin_scoring="wrong",
        now=NOW,
    )

    assert payload["status"] == KETER_SIGNAL_ORIGIN_SCORING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["scoring_recorded"] is False
    assert load_keter_signal_origin_scoring_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_keter_signal_origin_scoring(
        log_dir=tmp_path / "logs",
        record_scoring=True,
        confirm_keter_origin_scoring=CONFIRM_KETER_SIGNAL_ORIGIN_SCORING_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_keter_signal_origin_scoring_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == KETER_SIGNAL_ORIGIN_SCORING_RECORDED
    assert payload["scoring_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "KETER_SIGNAL_ORIGIN_SCORING"
    assert before_env == dict(os.environ)


def test_detector_available_origin_scores_above_registry_only_when_data_exists(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)
    hammer = _row(payload, "hammer_wick_reversal")
    crows = _row(payload, "three_black_crows")

    assert hammer["availability"] == "DETECTOR_AVAILABLE"
    assert crows["availability"] == "REGISTRY_ONLY"
    assert hammer["keter_score"] > crows["keter_score"]


def test_registry_only_three_black_crows_does_not_get_trading_ready_score(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)
    crows = _row(payload, "three_black_crows")

    assert crows["keter_score"] < 50
    assert crows["readiness"] == "ORIGIN_NEEDS_DETECTOR"
    assert "detector unavailable" in " ".join(crows["blockers"])


def test_three_black_crows_appears_in_detector_priority_recommendations(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)
    priorities = {row["signal_origin"]: row for row in payload["detector_priority_recommendations"]}

    assert priorities["three_black_crows"]["priority"] == "HIGH"
    assert "registry-only" in priorities["three_black_crows"]["reason"]


def test_hammer_wick_reversal_can_rank_highest_with_tagged_data(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs", hammer_count=6, golden_count=1, unknown_count=0)

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)

    assert payload["keter_origin_rankings"][0]["signal_origin"] == "hammer_wick_reversal"
    assert payload["current_best_origin"]["signal_origin"] == "hammer_wick_reversal"


def test_unknown_or_unclassified_is_penalized(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs", unknown_count=3)

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)
    unknown = _row(payload, "unknown_or_unclassified")

    assert unknown["keter_score"] <= 19
    assert unknown["readiness"] == "ORIGIN_UNKNOWN"
    assert "origin is unknown/unclassified" in " ".join(unknown["blockers"])


def test_live_authorized_false_and_paper_only_true_for_all_origins(tmp_path: Path) -> None:
    _write_origin_feed(tmp_path / "logs")

    payload = build_keter_signal_origin_scoring(log_dir=tmp_path / "logs", now=NOW)

    assert all(row["live_authorized"] is False for row in payload["keter_origin_rankings"])
    assert all(row["paper_only"] is True for row in payload["keter_origin_rankings"])
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["live_authorization_created"] is False


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_origin_feed(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_keter_signal_origin_scoring(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
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
    _write_origin_feed(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "keter-signal-origin-scoring",
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
    assert "keter_origin_rankings" in payload
    assert "by_lane_origin_scores" in payload
    assert "keter-signal-origin-scoring" in help_result.stdout


def _row(payload: dict, origin: str) -> dict:
    return next(row for row in payload["keter_origin_rankings"] if row["signal_origin"] == origin)


def _write_origin_feed(
    log_dir: Path,
    *,
    hammer_count: int = 2,
    golden_count: int = 1,
    unknown_count: int = 1,
) -> None:
    for index in range(hammer_count):
        _append_json(
            log_dir / "signals.ndjson",
            {
                "signal_id": f"hammer-{index}",
                "symbol": "BTCUSDT",
                "timeframe": "4m",
                "direction": "long",
                "hammer_strength": 90,
            },
        )
    for index in range(golden_count):
        _append_json(
            log_dir / "signals.ndjson",
            {
                "signal_id": f"gp-{index}",
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
            },
        )
    for index in range(unknown_count):
        _append_json(
            log_dir / "signals.ndjson",
            {
                "signal_id": f"unknown-{index}",
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "market",
            },
        )
    _append_json(
        log_dir / "multi_lane_evidence_rankings.ndjson",
        {
            "ranked_lanes": [
                {"lane_key": "BTCUSDT|4m|long|ladder_close_50_618", "score": 72},
                {"lane_key": "BTCUSDT|8m|short|ladder_close_50_618", "score": 64},
            ]
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
