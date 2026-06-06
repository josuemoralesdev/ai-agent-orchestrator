from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_event_tracker import (
    BETRAYAL_EVENT_TRACKER_RECORDED,
    BETRAYAL_EVENT_TRACKER_REJECTED,
    CONFIRM_BETRAYAL_EVENT_TRACKER_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_event_identity,
    build_betrayal_event_tracker,
    classify_betrayal_event_direction_context,
    load_betrayal_event_tracker_records,
    validate_betrayal_event_seed_schema,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_event_tracker(log_dir=log_dir, now=NOW)

    assert payload["record_tracker_requested"] is False
    assert payload["tracker_recorded"] is False
    assert payload["tracker_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_event_tracker(
        log_dir=log_dir,
        record_tracker=True,
        confirm_betrayal_event_tracker="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_EVENT_TRACKER_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["tracker_recorded"] is False
    assert load_betrayal_event_tracker_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_tracker_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_event_tracker(
        log_dir=log_dir,
        record_tracker=True,
        confirm_betrayal_event_tracker=CONFIRM_BETRAYAL_EVENT_TRACKER_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_event_tracker_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_EVENT_TRACKER_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["tracker_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_EVENT_TRACKER"
    assert before_env == dict(os.environ)


def test_builds_deterministic_event_identity_and_stable_hash() -> None:
    identity_one = build_betrayal_event_identity(
        symbol="BTCUSDT",
        timeframe="222m",
        candidate_label="222m aggregate",
        original_direction="long",
        inverse_direction="short",
        entry_mode="ladder_close_50_618",
        source_signal_id="sig-1",
        signal_timestamp=NOW.isoformat(),
        event_timeframe="222m",
        outcome_window=[1, 3, 5],
    )
    identity_two = build_betrayal_event_identity(
        symbol="BTCUSDT",
        timeframe="222m",
        candidate_label="222m aggregate",
        original_direction="long",
        inverse_direction="short",
        entry_mode="ladder_close_50_618",
        source_signal_id="sig-1",
        signal_timestamp=NOW.isoformat(),
        event_timeframe="222m",
        outcome_window=[1, 3, 5],
    )

    assert identity_one["event_identity"] == identity_two["event_identity"]
    assert identity_one["event_identity_hash"] == identity_two["event_identity_hash"]
    assert len(identity_one["event_identity_hash"]) == 64


def test_aggregate_only_candidate_is_context_seed_not_validated_proof(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_event_tracker(log_dir=log_dir, now=NOW)
    aggregate = next(row for row in payload["event_seed_candidates"] if row["candidate"] == "88m aggregate")
    record = next(row for row in payload["event_tracker_records_preview"] if row["candidate"] == "88m aggregate")

    assert aggregate["direction_context"] == "aggregate_context_only"
    assert aggregate["not_direction_specific"] is True
    assert aggregate["can_count_as_validated_sample_now"] is False
    assert record["can_count_as_validated_sample_now"] is False
    assert payload["event_tracker_gap_report"]["direction_split_missing"] is True


def test_direction_specific_event_requires_original_inverse_direction() -> None:
    complete = {
        "original_direction": "long",
        "inverse_direction": "short",
        "entry_mode": "ladder_close_50_618",
        "signal_timestamp": NOW.isoformat(),
    }
    missing_inverse = {
        "original_direction": "long",
        "entry_mode": "ladder_close_50_618",
        "signal_timestamp": NOW.isoformat(),
    }

    assert classify_betrayal_event_direction_context(complete) == "direction_specific"
    assert validate_betrayal_event_seed_schema(complete, direction_context="direction_specific")["schema_complete"] is True
    incomplete = validate_betrayal_event_seed_schema(missing_inverse, direction_context="direction_specific")
    assert incomplete["schema_complete"] is False
    assert "inverse_direction" in incomplete["missing_fields"]


def test_latest_222m_capture_can_be_seed_but_not_validated_sample(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_event_tracker(log_dir=log_dir, now=NOW)
    seed = next(row for row in payload["event_seed_candidates"] if row["candidate"] == "222m aggregate")

    assert seed["source"] == "full_spectrum_capture"
    assert seed["lane_key"] == "BTCUSDT|222m|long|ladder_close_50_618"
    assert seed["signal_timestamp"] == "2026-06-06T10:00:00+00:00"
    assert seed["can_track_future_outcome"] is True
    assert seed["can_count_as_validated_sample_now"] is False


def test_tracker_records_are_paper_only_not_live_or_promoted(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_event_tracker(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    for record in payload["event_tracker_records_preview"]:
        assert record["paper_only"] is True
        assert record["live_authorized"] is False
        assert record["promotion_allowed"] is False
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
        payload = build_betrayal_event_tracker(log_dir=log_dir, now=NOW)

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
            "betrayal-event-tracker",
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
    assert "event_seed_candidates" in payload
    assert "betrayal-event-tracker" in help_result.stdout


def _write_stack(log_dir: Path) -> None:
    _append_json(
        log_dir / "betrayal_paper_matrix_context.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_context_rows": [
                _matrix_row("222m", "BETRAYAL_PRIMARY_CANDIDATE", 15),
                _matrix_row("88m", "BETRAYAL_WATCHLIST", 32),
                _matrix_row("55m", "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY", 26),
            ],
            "safety": {"betrayal_live_authorized": False, "betrayal_promoted": False},
        },
    )
    _append_json(
        log_dir / "betrayal_true_inverse_refresh.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "candidate_true_inverse_summary": {
                "222m": _refresh("BETRAYAL_PRIMARY_CANDIDATE", 15),
                "88m": _refresh("BETRAYAL_WATCHLIST", 32),
                "55m": _refresh("BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY", 26),
            },
            "refresh_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
        },
    )
    _append_json(
        log_dir / "betrayal_integration_recheck.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_candidate_summary": {
                "222m": {"label": "BETRAYAL_PRIMARY_CANDIDATE"},
                "88m": {"label": "BETRAYAL_WATCHLIST"},
                "55m": {"label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY"},
            },
            "betrayal_capture_linkage": {
                "latest_222m_capture_found": True,
                "latest_222m_capture_lane": "BTCUSDT|222m|long|ladder_close_50_618",
                "latest_222m_capture_at": "2026-06-06T10:00:00+00:00",
                "can_use_capture_as_true_inverse_sample_now": False,
            },
        },
    )
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "captured_lanes": ["BTCUSDT|222m|long|ladder_close_50_618"],
            "capture_summary": {
                "candidate_examples_by_lane": {
                    "BTCUSDT|222m|long|ladder_close_50_618": [
                        {
                            "candidate_id": "BTCUSDT|222m|long|2026-06-06T10:00:00+00:00",
                            "lane_key": "BTCUSDT|222m|long|ladder_close_50_618",
                            "symbol": "BTCUSDT",
                            "timeframe": "222m",
                            "direction": "long",
                            "entry_mode": "ladder_close_50_618",
                            "timestamp": "2026-06-06T10:00:00+00:00",
                            "capture_allowed": True,
                        }
                    ]
                }
            },
        },
    )
    _append_json(
        log_dir / "betrayal_paper_signals.ndjson",
        {
            "emitted_signal_id": "betrayal-88m-signal",
            "symbol": "BTCUSDT",
            "timeframe": "88m",
            "source_signal_id": "source-88m",
            "signal_timestamp": "2026-06-06T09:00:00+00:00",
            "entry_mode": None,
        },
    )
    _append_json(
        log_dir / "betrayal_true_paper_outcomes.ndjson",
        {
            "outcome_id": "historical-not-r212-proof",
            "symbol": "BTCUSDT",
            "timeframe": "222m",
            "paper_only": True,
        },
    )


def _matrix_row(timeframe: str, label: str, resolved: int) -> dict:
    return {
        "candidate": f"{timeframe} aggregate",
        "label": label,
        "timeframe": timeframe,
        "resolved_true_inverse_samples": resolved,
        "validation_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _refresh(label: str, resolved: int) -> dict:
    return {
        "label": label,
        "resolved_true_inverse_samples": resolved,
        "shadow_outcome_count": resolved + 5,
        "unresolved_shadow_samples": 5,
        "validation_status": "TRUE_INVERSE_VALIDATION_REFRESHED",
    }


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
