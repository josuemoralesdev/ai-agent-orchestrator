from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_direction_split_resolver import (
    AGGREGATE_CONTEXT_ONLY,
    BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED,
    BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED,
    CONFIRM_BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_direction_split_resolver,
    extract_direction_from_lane_key,
    infer_inverse_direction,
    load_betrayal_direction_split_resolver_records,
    resolve_direction_split_candidate,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_split_resolver(log_dir=log_dir, now=NOW)

    assert payload["record_resolver_requested"] is False
    assert payload["resolver_recorded"] is False
    assert payload["resolver_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_split_resolver(
        log_dir=log_dir,
        record_resolver=True,
        confirm_betrayal_direction_split_resolver="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["resolver_recorded"] is False
    assert load_betrayal_direction_split_resolver_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_resolver_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_direction_split_resolver(
        log_dir=log_dir,
        record_resolver=True,
        confirm_betrayal_direction_split_resolver=CONFIRM_BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_direction_split_resolver_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["resolver_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_DIRECTION_SPLIT_RESOLVER"
    assert before_env == dict(os.environ)


def test_extracts_direction_from_explicit_lane_key() -> None:
    assert extract_direction_from_lane_key("BTCUSDT|88m|short|ladder_close_50_618") == "short"
    assert extract_direction_from_lane_key("BTCUSDT|88m|long|ladder_close_50_618") == "long"
    assert extract_direction_from_lane_key("BTCUSDT|88m|aggregate|ladder_close_50_618") is None


def test_inverse_direction_is_opposite_original_direction() -> None:
    assert infer_inverse_direction("long") == "short"
    assert infer_inverse_direction("short") == "long"
    assert infer_inverse_direction("aggregate") is None


def test_explicit_source_schema_resolves_direction_split() -> None:
    row = resolve_direction_split_candidate(
        {
            "candidate": "88m",
            "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
            "source_signal_id": "sig-88m",
            "signal_timestamp": NOW.isoformat(),
            "original_direction": "long",
            "betrayal_direction": "short",
            "entry_mode": "ladder_close_50_618",
        },
        source="betrayal_paper_signal",
    )

    assert row["direction_context"] == "direction_specific"
    assert row["original_direction"] == "long"
    assert row["inverse_direction"] == "short"
    assert row["direction_split_resolved"] is True
    assert row["can_enter_event_outcome_resolver"] is True
    assert row["can_count_as_validated_sample_now"] is False
    assert row["live_authorized"] is False


def test_aggregate_only_records_remain_unresolved(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_split_resolver(log_dir=log_dir, now=NOW)
    event_rows = [row for row in payload["direction_split_resolution_rows"] if row["source"] == "event_tracker"]

    assert event_rows
    assert {row["direction_context"] for row in event_rows} == {"aggregate_context_only"}
    assert all(row["direction_split_resolved"] is False for row in event_rows)
    assert payload["direction_split_status"] == AGGREGATE_CONTEXT_ONLY


def test_partial_records_do_not_resolve_without_original_source_direction() -> None:
    row = resolve_direction_split_candidate(
        {
            "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
            "source_signal_id": "capture-88m",
            "signal_timestamp": NOW.isoformat(),
            "entry_mode": "ladder_close_50_618",
        },
        candidate="88m aggregate",
        source="full_spectrum_capture",
    )

    assert row["source_direction"] == "short"
    assert row["direction_context"] == "partial"
    assert row["original_direction"] is None
    assert row["inverse_direction"] is None
    assert row["direction_split_resolved"] is False
    assert row["can_enter_event_outcome_resolver"] is False


def test_no_raw_capture_becomes_validated_sample_now(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir, include_capture=True)

    payload = build_betrayal_direction_split_resolver(log_dir=log_dir, now=NOW)
    capture_rows = [row for row in payload["direction_split_resolution_rows"] if row["source"] == "full_spectrum_capture"]

    assert capture_rows
    assert all(row["can_count_as_validated_sample_now"] is False for row in capture_rows)
    assert all(row["live_authorized"] is False for row in capture_rows)


def test_no_betrayal_promotion_or_live_authorization(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_split_resolver(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


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
        payload = build_betrayal_direction_split_resolver(log_dir=log_dir, now=NOW)

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
            "betrayal-direction-split-resolver",
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
    assert "direction_split_resolution_rows" in payload
    assert "betrayal-direction-split-resolver" in help_result.stdout


def _write_stack(log_dir: Path, *, include_capture: bool = False) -> None:
    _append_json(
        log_dir / "betrayal_regime_miro_recheck.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_regime_miro_candidate_rows": [
                {"candidate": "222m aggregate", "direction_split_resolved": False},
                {"candidate": "88m aggregate", "direction_split_resolved": False},
                {"candidate": "55m aggregate", "direction_split_resolved": False},
            ],
        },
    )
    _append_json(
        log_dir / "betrayal_event_tracker.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "event_seed_candidates": [
                _event_seed("222m", "BTCUSDT|222m|aggregate|ladder_close_50_618", None),
                _event_seed("88m", "BTCUSDT|88m|short|ladder_close_50_618", NOW.isoformat()),
                _event_seed("55m", "BTCUSDT|55m|short|ladder_close_50_618", NOW.isoformat()),
            ],
            "event_tracker_records_preview": [],
        },
    )
    _append_json(
        log_dir / "betrayal_paper_matrix_context.ndjson",
        {"generated_at": NOW.isoformat(), "betrayal_context_rows": []},
    )
    _append_json(
        log_dir / "betrayal_true_inverse_refresh.ndjson",
        {"generated_at": NOW.isoformat(), "candidate_true_inverse_summary": {}},
    )
    if include_capture:
        _append_json(
            log_dir / "full_spectrum_harvester_heartbeats.ndjson",
            {
                "generated_at": NOW.isoformat(),
                "capture_summary": {
                    "candidate_examples_by_lane": {
                        "BTCUSDT|88m|short|ladder_close_50_618": [
                            {
                                "candidate_id": "BTCUSDT|88m|short|2026-06-06T10:00:00+00:00",
                                "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                                "symbol": "BTCUSDT",
                                "timeframe": "88m",
                                "direction": "short",
                                "entry_mode": "ladder_close_50_618",
                                "timestamp": "2026-06-06T10:00:00+00:00",
                            }
                        ]
                    }
                },
            },
        )


def _event_seed(timeframe: str, lane_key: str, timestamp: str | None) -> dict:
    return {
        "candidate": f"{timeframe} aggregate",
        "source": "full_spectrum_capture",
        "lane_key": lane_key,
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "signal_timestamp": timestamp,
        "direction_context": "aggregate_context_only",
        "original_direction": None,
        "inverse_direction": None,
        "entry_mode": "ladder_close_50_618" if timestamp else None,
        "source_signal_id": f"BTCUSDT|{timeframe}|short|{timestamp}" if timestamp else None,
        "can_count_as_validated_sample_now": False,
    }


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
