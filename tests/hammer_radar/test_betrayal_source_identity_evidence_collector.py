import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_source_identity_evidence_collector import (
    BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED,
    BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_REJECTED,
    CONFIRM_BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDING_PHRASE,
    build_betrayal_source_identity_evidence_collector,
    build_deterministic_source_identity_preview,
    build_source_identity_evidence_rows,
    collect_source_identity_evidence,
    load_betrayal_source_identity_evidence_collector_records,
    parse_lane_key_for_entry_mode,
    parse_signal_id_for_identity_fields,
)
from src.app.hammer_radar.operator.betrayal_source_identity_normalizer import (
    CONFIRM_BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDING_PHRASE,
    build_betrayal_source_identity_normalizer,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import (
    CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
    build_strategy_evidence_registry,
    load_strategy_evidence_registry_records,
)

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_identity_evidence_collector(log_dir=log_dir, now=NOW)

    assert payload["record_collector_requested"] is False
    assert payload["collector_recorded"] is False
    assert load_betrayal_source_identity_evidence_collector_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_identity_evidence_collector(
        log_dir=log_dir,
        record_collector=True,
        confirm_betrayal_source_identity_evidence_collector="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["collector_recorded"] is False
    assert load_betrayal_source_identity_evidence_collector_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_collector_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_identity_evidence_collector(
        log_dir=log_dir,
        record_collector=True,
        confirm_betrayal_source_identity_evidence_collector=CONFIRM_BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_source_identity_evidence_collector_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR_RECORDED
    assert payload["collector_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_SOURCE_IDENTITY_EVIDENCE_COLLECTOR"


def test_parses_entry_mode_from_lane_key() -> None:
    parsed = parse_lane_key_for_entry_mode("BTCUSDT|88m|short|ladder_close_50_618")
    assert parsed["entry_mode"] == "ladder_close_50_618"
    assert parsed["evidence"] == "derived_from_lane_key"


def test_parses_identity_fields_from_signal_id_where_schema_supports_it() -> None:
    parsed = parse_signal_id_for_identity_fields("BTCUSDT|88m|short|2026-06-07T12:00:00+00:00|ladder_close_50_618")
    assert parsed["source_identity"].startswith("BTCUSDT|88m|short")
    assert parsed["symbol"] == "BTCUSDT"
    assert parsed["timeframe"] == "88m"
    assert parsed["direction"] == "short"
    assert parsed["entry_mode"] == "ladder_close_50_618"


def test_does_not_build_source_identity_from_candidate_label_alone() -> None:
    identity, evidence = collect_source_identity_evidence({"candidate": "88m aggregate", "timeframe": "88m"})

    assert identity is None
    assert evidence == "insufficient"


def test_builds_deterministic_source_identity_only_from_complete_local_fields() -> None:
    assert build_deterministic_source_identity_preview(
        symbol="BTCUSDT",
        timeframe="88m",
        original_direction="long",
        inverse_direction="short",
        entry_mode="ladder_close_50_618",
        timestamp=NOW.isoformat(),
        source_family="full_spectrum_capture",
    )
    assert (
        build_deterministic_source_identity_preview(
            symbol="BTCUSDT",
            timeframe="88m",
            original_direction="long",
            inverse_direction="short",
            entry_mode=None,
            timestamp=NOW.isoformat(),
            source_family="full_spectrum_capture",
        )
        is None
    )


def test_emits_resolver_ready_preview_only_when_all_registry_fields_exist(tmp_path: Path) -> None:
    registry = _registry_manifest(tmp_path / "logs")
    rows = build_source_identity_evidence_rows(
        strategy_evidence_registry={"registry_manifest": registry},
        betrayal_source_identity_normalizer={},
        registry_wiring_betrayal_source_family={},
        betrayal_aggregate_decomposition={},
        betrayal_source_emitter_refresh={"direction_specific_source_preview": [_complete_v2_row()]},
        betrayal_direction_split_resolver={},
        betrayal_event_tracker={},
        full_spectrum_capture_records=[],
        betrayal_shadow_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["resolver_ready_preview"] is True
    assert rows[0]["schema_complete_preview"] is True
    blocked_rows = build_source_identity_evidence_rows(
        strategy_evidence_registry={"registry_manifest": registry},
        betrayal_source_identity_normalizer={},
        registry_wiring_betrayal_source_family={},
        betrayal_aggregate_decomposition={"decomposition_rows": [{"candidate": "88m aggregate", "timeframe": "88m"}]},
        betrayal_source_emitter_refresh={},
        betrayal_direction_split_resolver={},
        betrayal_event_tracker={},
        full_spectrum_capture_records=[],
        betrayal_shadow_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )
    assert blocked_rows[0]["resolver_ready_preview"] is False


def test_all_rows_remain_paper_only_no_live_no_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_source_identity_evidence_collector(log_dir=log_dir, now=NOW)

    assert all(row["paper_only"] is True for row in payload["source_identity_evidence_rows"])
    assert all(row["live_authorized"] is False for row in payload["source_identity_evidence_rows"])
    assert all(row["promotion_allowed"] is False for row in payload["source_identity_evidence_rows"])
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_no_env_config_mutation_or_destructive_ledger_rewrite(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    payload = build_betrayal_source_identity_evidence_collector(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_env == dict(os.environ)
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["ledger_rewritten"] is False
    assert payload["safety"]["destructive_write"] is False


def test_no_binance_network_order_live_transfer_or_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_source_identity_evidence_collector(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
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
            "betrayal-source-identity-evidence-collector",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["target_scope"]["family"] == "betrayal"
    assert payload["input_summary"]["registry_found"] is True


def _write_stack(log_dir: Path) -> None:
    _write_registry(log_dir)
    _write_ndjson(
        log_dir / "betrayal_aggregate_decomposition.ndjson",
        {
            "decomposition_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": None,
                    "inverse_direction": None,
                    "entry_mode": None,
                    "source_identity": None,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
            "v2_source_rows_preview": [],
        },
    )
    _write_ndjson(
        log_dir / "betrayal_source_emitter_refresh.ndjson",
        {
            "source_candidate_rows": [
                {
                    "candidate": "55m aggregate_if_available",
                    "timeframe": "55m",
                    "original_direction": "long",
                    "inverse_direction": "short",
                    "source_signal_id": "BTCUSDT|55m|long|2026-06-07T12:00:00+00:00|ladder_close_50_618",
                    "signal_timestamp": NOW.isoformat(),
                    "lane_key": "BTCUSDT|55m|short|ladder_close_50_618",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
            "direction_specific_source_preview": [_complete_v2_row()],
        },
    )
    _write_ndjson(
        log_dir / "betrayal_direction_split_resolver.ndjson",
        {
            "direction_split_resolution_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": "short",
                    "inverse_direction": "long",
                    "entry_mode": None,
                    "source_identity": None,
                    "source_signal_id": None,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ]
        },
    )
    _write_ndjson(
        log_dir / "betrayal_event_tracker.ndjson",
        {
            "event_tracker_records_preview": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "original_direction": None,
                    "inverse_direction": None,
                    "entry_mode": "ladder_close_50_618",
                    "source_signal_id": "BTCUSDT|88m|short|2026-06-07T12:00:00+00:00",
                    "source_capture_id": "BTCUSDT|88m|short|2026-06-07T12:00:00+00:00",
                    "signal_timestamp": NOW.isoformat(),
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ]
        },
    )
    _write_ndjson(log_dir / "betrayal_shadow_outcomes.ndjson", {"symbol": "BTCUSDT", "timeframe": "222m", "shadow_direction": "short"})
    _write_ndjson(
        log_dir / "full_spectrum_harvester_expansion.ndjson",
        {
            "capture_summary": {
                "captured_candidates": [
                    {
                        "candidate_id": "BTCUSDT|22m|short|2026-06-07T12:00:00+00:00",
                        "symbol": "BTCUSDT",
                        "timeframe": "22m",
                        "direction": "short",
                        "entry_mode": "ladder_close_50_618",
                        "lane_key": "BTCUSDT|22m|short|ladder_close_50_618",
                        "timestamp": NOW.isoformat(),
                    }
                ]
            }
        },
    )
    build_betrayal_source_identity_normalizer(
        log_dir=log_dir,
        record_normalizer=True,
        confirm_betrayal_source_identity_normalizer=CONFIRM_BETRAYAL_SOURCE_IDENTITY_NORMALIZER_RECORDING_PHRASE,
        now=NOW,
    )


def _write_registry(log_dir: Path) -> None:
    build_strategy_evidence_registry(
        log_dir=log_dir,
        record_registry=True,
        confirm_strategy_evidence_registry=CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
        now=NOW,
    )


def _registry_manifest(log_dir: Path) -> dict[str, object]:
    _write_registry(log_dir)
    return load_strategy_evidence_registry_records(log_dir=log_dir, limit=0)[0]["registry_manifest"]


def _complete_v2_row(*, candidate: str = "222m aggregate", timeframe: str = "222m") -> dict[str, object]:
    return {
        "schema_version": "betrayal_source_emitter_v2",
        "source_type": "betrayal_source_emitter",
        "candidate": candidate,
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "entry_mode": "ladder_close_50_618",
        "original_direction": "long",
        "inverse_direction": "short",
        "emitted_direction": "short",
        "source_identity": f"source-{timeframe}",
        "source_signal_id": f"signal-{timeframe}",
        "emitted_signal_id": f"emitted-{timeframe}",
        "source_signal_timestamp": NOW.isoformat(),
        "emitted_at": NOW.isoformat(),
        "lane_key": f"BTCUSDT|{timeframe}|short|ladder_close_50_618",
        "betrayal_event_identity": f"identity-{timeframe}",
        "betrayal_event_identity_hash": f"hash-{timeframe}",
        "outcome_windows": [1, 3, 5, 10, 21, 34, 55],
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _write_ndjson(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
