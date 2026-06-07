from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_aggregate_decomposition import (
    AGGREGATE_DECOMPOSITION_BLOCKED,
    AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS,
    AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY,
    BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED,
    BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED,
    CONFIRM_BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_aggregate_decomposition,
    build_decomposition_candidate,
    build_v2_source_rows_preview,
    load_betrayal_aggregate_decomposition_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_aggregate_decomposition(log_dir=log_dir, now=NOW)

    assert payload["record_decomposition_requested"] is False
    assert payload["decomposition_recorded"] is False
    assert payload["decomposition_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_aggregate_decomposition(
        log_dir=log_dir,
        record_decomposition=True,
        confirm_betrayal_aggregate_decomposition="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["decomposition_recorded"] is False
    assert load_betrayal_aggregate_decomposition_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_decomposition_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_aggregate_decomposition(
        log_dir=log_dir,
        record_decomposition=True,
        confirm_betrayal_aggregate_decomposition=CONFIRM_BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_aggregate_decomposition_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["decomposition_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_AGGREGATE_DECOMPOSITION"
    assert before_env == dict(os.environ)


def test_ready_row_requires_direction_entry_identity_and_timestamp() -> None:
    row = build_decomposition_candidate(
        {
            "evidence_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": "long",
                    "inverse_direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "source_identity": "source-88",
                    "source_signal_id": "sig-88",
                    "signal_timestamp": NOW.isoformat(),
                    "evidence_source": "betrayal_paper_signal",
                }
            ]
        }
    )

    assert row["decomposition_status"] == AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS
    assert row["ready_for_v2_source_row"] is True
    assert row["can_enter_event_outcome_resolver"] is True
    assert row["can_count_as_validated_sample_now"] is False
    assert row["paper_only"] is True
    assert row["live_authorized"] is False


def test_partial_row_with_missing_source_identity_stays_partial() -> None:
    row = build_decomposition_candidate(
        {
            "evidence_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": "long",
                    "inverse_direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "signal_timestamp": NOW.isoformat(),
                    "evidence_source": "shadow_outcome",
                }
            ]
        }
    )

    assert row["decomposition_status"] == AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY
    assert row["ready_for_v2_source_row"] is False
    assert row["can_enter_event_outcome_resolver"] is False


def test_lane_direction_alone_is_not_enough() -> None:
    row = build_decomposition_candidate(
        {
            "evidence_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "capture-88",
                    "signal_timestamp": NOW.isoformat(),
                    "evidence_source": "full_spectrum_capture",
                }
            ]
        }
    )

    assert row["lane_direction"] == "short"
    assert row["original_direction"] is None
    assert row["inverse_direction"] is None
    assert row["decomposition_status"] == AGGREGATE_DECOMPOSITION_BLOCKED
    assert row["ready_for_v2_source_row"] is False


def test_aggregate_only_row_stays_blocked() -> None:
    row = build_decomposition_candidate(
        {
            "evidence_rows": [
                {
                    "candidate": "222m aggregate",
                    "timeframe": "222m",
                    "direction_context": "aggregate_context_only",
                    "evidence_source": "event_tracker",
                }
            ]
        }
    )

    assert row["decomposition_status"] == AGGREGATE_DECOMPOSITION_BLOCKED
    assert row["ready_for_v2_source_row"] is False


def test_v2_source_row_preview_only_includes_complete_rows() -> None:
    ready = build_decomposition_candidate(
        {
            "evidence_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": "long",
                    "inverse_direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "source_identity": "source-88",
                    "source_signal_id": "sig-88",
                    "signal_timestamp": NOW.isoformat(),
                    "evidence_source": "betrayal_paper_signal",
                }
            ]
        }
    )
    blocked = build_decomposition_candidate(
        {"evidence_rows": [{"candidate": "222m aggregate", "timeframe": "222m", "evidence_source": "event_tracker"}]}
    )

    preview = build_v2_source_rows_preview(decomposition_rows=[ready, blocked], generated_at=NOW)

    assert len(preview) == 1
    assert preview[0]["schema_version"] == "betrayal_source_emitter_v2"
    assert preview[0]["schema_complete"] is True
    assert preview[0]["candidate"] == "88m aggregate"
    assert preview[0]["paper_only"] is True
    assert preview[0]["live_authorized"] is False
    assert preview[0]["promotion_allowed"] is False


def test_no_raw_capture_becomes_validated_sample_now(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir, include_capture=True)

    payload = build_betrayal_aggregate_decomposition(log_dir=log_dir, now=NOW)

    assert payload["decomposition_rows"]
    assert all(row["can_count_as_validated_sample_now"] is False for row in payload["decomposition_rows"])


def test_no_betrayal_promotion_or_live_authorization(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_aggregate_decomposition(log_dir=log_dir, now=NOW)

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
        payload = build_betrayal_aggregate_decomposition(log_dir=log_dir, now=NOW)

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
            "betrayal-aggregate-decomposition",
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
    assert "decomposition_rows" in payload
    assert "betrayal-aggregate-decomposition" in help_result.stdout


def _write_stack(log_dir: Path, *, include_capture: bool = False) -> None:
    _append_json(
        log_dir / "betrayal_source_emitter_refresh.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "source_candidate_rows": [
                {
                    "candidate": "222m aggregate",
                    "timeframe": "222m",
                    "entry_mode": None,
                    "source_identity": None,
                    "source_signal_id": None,
                    "signal_timestamp": None,
                }
            ],
        },
    )
    _append_json(
        log_dir / "betrayal_direction_split_resolver.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "direction_split_resolution_rows": [
                {
                    "candidate": "88m aggregate",
                    "direction_context": "partial",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "capture-88",
                    "signal_timestamp": NOW.isoformat(),
                },
                {
                    "candidate": "55m aggregate",
                    "direction_context": "aggregate_context_only",
                    "lane_key": "BTCUSDT|55m|short|ladder_close_50_618",
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "capture-55",
                    "signal_timestamp": NOW.isoformat(),
                },
            ],
        },
    )
    _append_json(
        log_dir / "betrayal_event_tracker.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "event_seed_candidates": [
                {
                    "candidate": "222m aggregate",
                    "timeframe": "222m",
                    "direction_context": "aggregate_context_only",
                }
            ],
        },
    )
    _append_json(log_dir / "betrayal_true_inverse_refresh.ndjson", {"generated_at": NOW.isoformat()})
    _append_json(
        log_dir / "betrayal_shadow_outcomes.ndjson",
        {
            "candidate": "88m aggregate",
            "timeframe": "88m",
            "original_direction": "long",
            "inverse_direction": "short",
            "entry_mode": "ladder_close_50_618",
            "source_identity": "shadow-88",
            "source_signal_id": "sig-88",
            "signal_timestamp": NOW.isoformat(),
        },
    )
    if include_capture:
        _append_json(
            log_dir / "full_spectrum_harvester_expansion.ndjson",
            {
                "capture_summary": {
                    "candidate_examples_by_lane": {
                        "BTCUSDT|88m|short|ladder_close_50_618": [
                            {
                                "candidate": "88m aggregate",
                                "timeframe": "88m",
                                "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                                "entry_mode": "ladder_close_50_618",
                                "source_signal_id": "capture-88",
                                "signal_timestamp": NOW.isoformat(),
                            }
                        ]
                    }
                }
            },
        )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
