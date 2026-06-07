from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
    BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED,
    CONFIRM_REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_BLOCKED,
    REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED,
    REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED,
    build_registry_backed_betrayal_candidate_view,
    build_registry_wiring_betrayal_source_family,
    load_latest_strategy_evidence_registry,
    load_registry_wiring_betrayal_source_family_records,
    validate_betrayal_source_row_against_registry,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import (
    CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
    build_strategy_evidence_registry,
)

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)

    assert payload["record_wiring_requested"] is False
    assert payload["wiring_recorded"] is False
    assert payload["wiring_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_registry_wiring_betrayal_source_family(
        log_dir=log_dir,
        record_wiring=True,
        confirm_registry_wiring_betrayal_source_family="wrong",
        now=NOW,
    )

    assert payload["status"] == REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["wiring_recorded"] is False
    assert load_registry_wiring_betrayal_source_family_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_wiring_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_registry_wiring_betrayal_source_family(
        log_dir=log_dir,
        record_wiring=True,
        confirm_registry_wiring_betrayal_source_family=CONFIRM_REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_registry_wiring_betrayal_source_family_records(log_dir=log_dir, limit=0)

    assert payload["status"] == REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["wiring_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY"
    assert before_env == dict(os.environ)


def test_loads_registry_manifest(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)

    registry = load_latest_strategy_evidence_registry(log_dir=log_dir)

    assert registry["registry_validation"]["valid"] is True
    assert "betrayal_candidates" in registry["registry_manifest"]


def test_blocks_if_registry_missing(tmp_path: Path) -> None:
    payload = build_registry_wiring_betrayal_source_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY_BLOCKED
    assert payload["input_summary"]["strategy_evidence_registry_found"] is False
    assert payload["registry_wiring_gap_report"]["registry_missing"] is True
    assert payload["wiring_recorded"] is False


def test_validates_betrayal_candidates_from_registry(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)
    candidates = {row["candidate_id"]: row for row in payload["candidate_registry_validation"]}

    assert set(candidates) == {"222m_aggregate", "88m_aggregate", "55m_aggregate_if_available"}
    assert all(row["exists_in_registry"] is True for row in candidates.values())
    assert all(row["validation_status"] == "valid" for row in candidates.values())


def test_validates_betrayal_source_emitter_v2_required_fields_from_registry(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    registry = load_latest_strategy_evidence_registry(log_dir=log_dir)["registry_manifest"]
    view = build_registry_backed_betrayal_candidate_view(registry)

    validation = validate_betrayal_source_row_against_registry(_complete_v2_row(), registry_manifest=registry)

    assert "source_identity" in view["required_source_fields"]
    assert "betrayal_event_identity_hash" in view["required_source_fields"]
    assert validation["row_status"] == "registry_valid"
    assert validation["schema_complete"] is True
    assert validation["blocked_from_resolver"] is False


def test_missing_entry_mode_source_identity_rows_remain_blocked(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir, include_complete=False)

    payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)

    assert payload["registry_backed_missing_field_report"]["missing_entry_mode_rows"] >= 1
    assert payload["registry_backed_missing_field_report"]["missing_source_identity_rows"] >= 1
    assert payload["registry_backed_missing_field_report"]["resolver_ready_rows"] == 0
    assert payload["wiring_status"] == BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED


def test_all_registry_backed_rows_remain_paper_only_and_not_live(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert all(row["paper_only"] is True for row in payload["candidate_registry_validation"])
    assert all(row["live_authorized"] is False for row in payload["candidate_registry_validation"])
    assert all(row["live_authorized"] is False for row in payload["source_row_registry_validation"])


def test_no_betrayal_promotion_env_config_mutation_or_destructive_rewrite(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_env == dict(os.environ)
    assert payload["safety"]["betrayal_promoted"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["env_mutated"] is False
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
        payload = build_registry_wiring_betrayal_source_family(log_dir=log_dir, now=NOW)

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
            "registry-wiring-betrayal-source-family",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["target_scope"]["family"] == "betrayal"
    assert payload["input_summary"]["strategy_evidence_registry_found"] is True


def _write_stack(log_dir: Path, *, include_complete: bool = True) -> None:
    _write_registry(log_dir)
    _write_ndjson(
        log_dir / "betrayal_aggregate_decomposition.ndjson",
        {
            "decomposition_rows": [
                {
                    "candidate": "222m aggregate",
                    "timeframe": "222m",
                    "original_direction": "long",
                    "inverse_direction": "short",
                    "entry_mode": None,
                    "source_identity": None,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
            "v2_source_rows_preview": [_complete_v2_row()] if include_complete else [],
        },
    )
    _write_ndjson(
        log_dir / "betrayal_source_emitter_refresh.ndjson",
        {
            "source_candidate_rows": [
                {
                    "candidate": "88m aggregate",
                    "timeframe": "88m",
                    "entry_mode": "entry_unknown",
                    "original_direction": "short",
                    "inverse_direction": "long",
                    "emitted_direction": "long",
                    "source_identity": "",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
            "direction_specific_source_preview": [_complete_v2_row(candidate="88m aggregate", timeframe="88m")] if include_complete else [],
        },
    )
    _write_ndjson(
        log_dir / "betrayal_direction_split_resolver.ndjson",
        {
            "direction_split_resolution_rows": [
                {
                    "candidate": "55m aggregate",
                    "timeframe": "55m",
                    "original_direction": None,
                    "inverse_direction": None,
                    "entry_mode": "ladder_close_50_618",
                    "source_identity": None,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ]
        },
    )


def _write_registry(log_dir: Path) -> None:
    build_strategy_evidence_registry(
        log_dir=log_dir,
        record_registry=True,
        confirm_strategy_evidence_registry=CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
        now=NOW,
    )


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
        "outcome_windows": [1, 3, 5],
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _write_ndjson(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
