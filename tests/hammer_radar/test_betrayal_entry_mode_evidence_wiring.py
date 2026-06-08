import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_entry_mode_evidence_wiring import (
    BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED,
    BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_REJECTED,
    CONFIRM_BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDING_PHRASE,
    build_betrayal_entry_mode_evidence_wiring,
    build_entry_mode_evidence_rows,
    build_entry_mode_propagation_contract,
    extract_entry_mode_from_lane_key,
    extract_entry_mode_from_signal_id,
    load_betrayal_entry_mode_evidence_wiring_records,
    validate_entry_mode_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import (
    CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
    build_strategy_evidence_registry,
)

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_evidence_wiring(log_dir=log_dir, now=NOW)

    assert payload["record_wiring_requested"] is False
    assert payload["wiring_recorded"] is False
    assert load_betrayal_entry_mode_evidence_wiring_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_evidence_wiring(
        log_dir=log_dir,
        record_wiring=True,
        confirm_betrayal_entry_mode_evidence_wiring="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["wiring_recorded"] is False
    assert load_betrayal_entry_mode_evidence_wiring_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_wiring_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_evidence_wiring(
        log_dir=log_dir,
        record_wiring=True,
        confirm_betrayal_entry_mode_evidence_wiring=CONFIRM_BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_entry_mode_evidence_wiring_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING_RECORDED
    assert payload["wiring_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_ENTRY_MODE_EVIDENCE_WIRING"


def test_extracts_entry_mode_from_lane_key() -> None:
    assert extract_entry_mode_from_lane_key("BTCUSDT|88m|short|ladder_close_50_618") == "ladder_close_50_618"
    assert extract_entry_mode_from_lane_key("BTCUSDT|88m|short") is None


def test_extracts_entry_mode_from_signal_id_when_schema_supports_it(tmp_path: Path) -> None:
    registry = _registry_manifest(tmp_path / "logs")

    assert (
        extract_entry_mode_from_signal_id(
            "BTCUSDT|88m|short|2026-06-07T12:00:00+00:00|ladder_close_50_618",
            registry_manifest=registry,
        )
        == "ladder_close_50_618"
    )


def test_rejects_common_default_inference(tmp_path: Path) -> None:
    registry = _registry_manifest(tmp_path / "logs")
    rows = build_entry_mode_evidence_rows(
        source_identity_evidence_collector={"source_identity_evidence_rows": [{"candidate": "88m aggregate", "timeframe": "88m"}]},
        source_identity_normalizer={},
        strategy_evidence_registry={"registry_manifest": registry},
        registry_wiring_betrayal_source_family={},
        betrayal_aggregate_decomposition={},
        betrayal_source_emitter_refresh={},
        betrayal_direction_split_resolver={},
        betrayal_event_tracker={},
        full_spectrum_capture_records=[],
    )

    assert rows[0]["entry_mode"] is None
    assert rows[0]["entry_mode_source"] == "insufficient"
    assert rows[0]["can_feed_source_identity_normalizer"] is False


def test_rejects_unknown_and_entry_unknown(tmp_path: Path) -> None:
    registry = _registry_manifest(tmp_path / "logs")

    assert validate_entry_mode_against_registry("unknown", registry)["valid"] is False
    assert validate_entry_mode_against_registry("entry_unknown", registry)["valid"] is False


def test_validates_entry_mode_against_registry(tmp_path: Path) -> None:
    registry = _registry_manifest(tmp_path / "logs")

    valid = validate_entry_mode_against_registry("ladder_close_50_618", registry)
    invalid = validate_entry_mode_against_registry("not_in_registry", registry)

    assert valid["valid"] is True
    assert valid["registry_entry_mode_found"] is True
    assert invalid["valid"] is False
    assert invalid["registry_entry_mode_found"] is False


def test_creates_propagation_contract() -> None:
    contract = build_entry_mode_propagation_contract()

    assert contract["contract_name"] == "betrayal_entry_mode_source_contract_v1"
    assert "entry_mode" in contract["required_for_future_emitters"]
    assert contract["entry_mode_must_exist_in_registry"] is True
    assert contract["common_default_inference_allowed"] is False
    assert contract["paper_only"] is True
    assert contract["live_authorized"] is False


def test_does_not_mark_resolver_ready_rows(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_evidence_wiring(log_dir=log_dir, now=NOW)

    assert payload["entry_mode_evidence_rows"]
    assert all(row["can_feed_resolver_ready_preview"] is False for row in payload["entry_mode_evidence_rows"])


def test_all_rows_remain_paper_only_live_false_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_evidence_wiring(log_dir=log_dir, now=NOW)

    assert all(row["paper_only"] is True for row in payload["entry_mode_evidence_rows"])
    assert all(row["live_authorized"] is False for row in payload["entry_mode_evidence_rows"])
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

    payload = build_betrayal_entry_mode_evidence_wiring(log_dir=log_dir, now=NOW)

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
        payload = build_betrayal_entry_mode_evidence_wiring(log_dir=log_dir, now=NOW)

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
            "betrayal-entry-mode-evidence-wiring",
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
    registry = _registry_manifest(log_dir)
    _write_ndjson(
        log_dir / "betrayal_source_identity_evidence_collector.ndjson",
        {
            "source_identity_evidence_summary": {"resolver_ready_preview_rows": 0},
            "source_identity_evidence_rows": [
                {
                    "candidate": "88m aggregate",
                    "source": "collector",
                    "symbol": "BTCUSDT",
                    "timeframe": "88m",
                    "entry_mode": "ladder_close_50_618",
                    "lane_key": "BTCUSDT|88m|short|ladder_close_50_618",
                    "source_signal_id": "BTCUSDT|88m|short|2026-06-07T12:00:00+00:00",
                    "timestamp": NOW.isoformat(),
                    "paper_only": True,
                    "live_authorized": False,
                },
                {
                    "candidate": "55m aggregate",
                    "source": "collector",
                    "symbol": "BTCUSDT",
                    "timeframe": "55m",
                    "source_signal_id": "BTCUSDT|55m|short|2026-06-07T12:00:00+00:00|ladder_close_50_618",
                    "timestamp": NOW.isoformat(),
                    "paper_only": True,
                    "live_authorized": False,
                },
                {
                    "candidate": "222m aggregate",
                    "source": "collector",
                    "symbol": "BTCUSDT",
                    "timeframe": "222m",
                    "timestamp": NOW.isoformat(),
                    "paper_only": True,
                    "live_authorized": False,
                },
            ],
        },
    )
    _write_ndjson(
        log_dir / "betrayal_source_identity_normalizer.ndjson",
        {
            "normalized_source_rows_preview": [
                {
                    "candidate": "44m aggregate",
                    "source": "normalizer",
                    "symbol": "BTCUSDT",
                    "timeframe": "44m",
                    "entry_mode": "entry_unknown",
                    "timestamp": NOW.isoformat(),
                    "paper_only": True,
                    "live_authorized": False,
                }
            ]
        },
    )
    _write_ndjson(log_dir / "registry_wiring_betrayal_source_family.ndjson", {"registry_valid": True})
    _write_ndjson(log_dir / "betrayal_aggregate_decomposition.ndjson", {"decomposition_rows": []})
    _write_ndjson(log_dir / "betrayal_source_emitter_refresh.ndjson", {"direction_specific_source_preview": []})
    _write_ndjson(log_dir / "betrayal_direction_split_resolver.ndjson", {"direction_split_rows": []})
    _write_ndjson(log_dir / "betrayal_event_tracker.ndjson", {"event_rows": []})
    _write_ndjson(
        log_dir / "full_spectrum_harvester_expansion.ndjson",
        {
            "capture_summary": {
                "captured_candidates": [
                    {
                        "candidate_id": "BTCUSDT|8m|short|2026-06-07T12:00:00+00:00",
                        "signal_id": "BTCUSDT|8m|short|2026-06-07T12:00:00+00:00",
                        "lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
                        "symbol": "BTCUSDT",
                        "timeframe": "8m",
                        "entry_mode": "ladder_close_50_618",
                        "timestamp": NOW.isoformat(),
                        "paper_only": True,
                        "live_authorized": False,
                    }
                ]
            }
        },
    )
    assert registry["entry_modes"]


def _registry_manifest(log_dir: Path) -> dict:
    payload = build_strategy_evidence_registry(
        log_dir=log_dir,
        record_registry=True,
        confirm_strategy_evidence_registry=CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
        now=NOW,
    )
    return payload["registry_manifest"]


def _write_ndjson(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
