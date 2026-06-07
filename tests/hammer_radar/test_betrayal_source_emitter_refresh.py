from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_source_emitter_refresh import (
    BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED,
    BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED,
    CONFIRM_BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDING_PHRASE,
    LEDGER_FILENAME,
    SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED,
    build_betrayal_source_candidate_rows,
    build_betrayal_source_emitter_refresh,
    build_direction_specific_source_preview,
    build_refreshed_betrayal_source_contract,
    load_betrayal_source_emitter_refresh_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_emitter_refresh(log_dir=log_dir, now=NOW)

    assert payload["record_refresh_requested"] is False
    assert payload["refresh_recorded"] is False
    assert payload["refresh_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_emitter_refresh(
        log_dir=log_dir,
        record_refresh=True,
        confirm_betrayal_source_emitter_refresh="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["refresh_recorded"] is False
    assert load_betrayal_source_emitter_refresh_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_refresh_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_source_emitter_refresh(
        log_dir=log_dir,
        record_refresh=True,
        confirm_betrayal_source_emitter_refresh=CONFIRM_BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_source_emitter_refresh_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["refresh_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_SOURCE_EMITTER_REFRESH"
    assert before_env == dict(os.environ)


def test_refreshed_contract_includes_direction_fields() -> None:
    contract = build_refreshed_betrayal_source_contract()

    assert contract["schema_version"] == "betrayal_source_emitter_v2"
    assert "original_direction" in contract["required_fields"]
    assert "inverse_direction" in contract["required_fields"]
    assert "emitted_direction" in contract["required_fields"]
    assert contract["direction_fields_required"] is True
    assert contract["paper_only"] is True
    assert contract["live_authorized"] is False


def test_aggregate_decomposition_is_required(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_emitter_refresh(log_dir=log_dir, now=NOW)

    assert payload["source_emitter_status"] == SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED
    assert payload["source_emitter_gap_report"]["aggregate_rows_blocked"] >= 1
    assert payload["aggregate_decomposition_requirements"]["88m aggregate"]


def test_lane_direction_alone_is_not_enough() -> None:
    rows = build_betrayal_source_candidate_rows(
        direction_split_resolver={
            "direction_split_resolution_rows": [
                {
                    "candidate": "88m aggregate",
                    "direction_context": "partial",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "capture-88",
                    "signal_timestamp": NOW.isoformat(),
                }
            ]
        },
        event_tracker={},
        paper_matrix_context={},
        true_inverse_refresh={},
        existing_betrayal_paper_signals=[],
    )
    row = next(item for item in rows if item["candidate"] == "88m aggregate")

    assert row["source_direction"] == "short"
    assert row["can_emit_direction_specific_now"] is False
    assert row["aggregate_decomposition_required"] is True
    assert "original_direction" in row["missing_fields"]
    assert "inverse_direction" in row["missing_fields"]


def test_incomplete_rows_are_blocked(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_emitter_refresh(log_dir=log_dir, now=NOW)
    preview = next(row for row in payload["direction_specific_source_preview"] if row["candidate"] == "88m aggregate")

    assert preview["schema_complete"] is False
    assert preview["blocked_from_event_outcome_resolver"] is True
    assert preview["original_direction"] is None
    assert preview["emitted_direction"] is None


def test_direction_specific_source_preview_uses_explicit_inverse_direction() -> None:
    rows = build_betrayal_source_candidate_rows(
        direction_split_resolver={
            "direction_split_resolution_rows": [
                {
                    "candidate": "88m aggregate",
                    "direction_context": "direction_specific",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "sig-88",
                    "signal_timestamp": NOW.isoformat(),
                    "original_direction": "long",
                    "inverse_direction": "short",
                }
            ]
        },
        event_tracker={},
        paper_matrix_context={},
        true_inverse_refresh={},
        existing_betrayal_paper_signals=[],
    )
    preview = build_direction_specific_source_preview(source_candidate_rows=rows, generated_at=NOW)
    row = next(item for item in preview if item["candidate"] == "88m aggregate")

    assert row["schema_complete"] is True
    assert row["original_direction"] == "long"
    assert row["inverse_direction"] == "short"
    assert row["emitted_direction"] == "short"
    assert row["paper_only"] is True
    assert row["live_authorized"] is False
    assert row["promotion_allowed"] is False


def test_paper_only_live_false_and_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_emitter_refresh(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    for row in payload["source_candidate_rows"]:
        assert row["paper_only"] is True
        assert row["live_authorized"] is False
        assert row["promotion_allowed"] is False
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
        payload = build_betrayal_source_emitter_refresh(log_dir=log_dir, now=NOW)

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
            "betrayal-source-emitter-refresh",
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
    assert "refreshed_source_contract" in payload
    assert "betrayal-source-emitter-refresh" in help_result.stdout


def _write_stack(log_dir: Path) -> None:
    _append_json(
        log_dir / "betrayal_direction_split_resolver.ndjson",
        {
            "status": "BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED",
            "direction_split_status": "DIRECTION_SPLIT_PARTIAL",
            "direction_split_resolution_rows": [
                {
                    "candidate": "222m aggregate",
                    "direction_context": "aggregate_context_only",
                    "lane_key": "BTCUSDT|222m|aggregate|ladder_close_50_618",
                    "entry_mode": None,
                    "original_direction": None,
                    "inverse_direction": None,
                    "source_signal_id": None,
                    "signal_timestamp": None,
                },
                {
                    "candidate": "88m aggregate",
                    "direction_context": "partial",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "original_direction": None,
                    "inverse_direction": None,
                    "source_signal_id": "capture-88",
                    "signal_timestamp": "2026-06-06T12:39:59.999000+00:00",
                },
                {
                    "candidate": "55m aggregate",
                    "direction_context": "aggregate_context_only",
                    "lane_key": "BTCUSDT|55m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "original_direction": None,
                    "inverse_direction": None,
                    "source_signal_id": "capture-55",
                    "signal_timestamp": "2026-06-06T13:34:59.999000+00:00",
                },
            ],
        },
    )
    _append_json(
        log_dir / "betrayal_event_tracker.ndjson",
        {
            "status": "BETRAYAL_EVENT_TRACKER_RECORDED",
            "event_tracker_records_preview": [
                {
                    "candidate": "88m aggregate",
                    "direction_context": "aggregate_context_only",
                    "symbol": "BTCUSDT",
                    "timeframe": "88m",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "capture-88",
                    "signal_timestamp": "2026-06-06T12:39:59.999000+00:00",
                }
            ],
        },
    )
    _append_json(log_dir / "betrayal_paper_matrix_context.ndjson", {"status": "OK"})
    _append_json(log_dir / "betrayal_true_inverse_refresh.ndjson", {"status": "OK"})


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
