from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_registry_consumer_refactor import (
    BETRAYAL_REGISTRY_CONSUMER_REFACTOR_BLOCKED,
    BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED,
    BETRAYAL_REGISTRY_CONSUMER_REFACTOR_REJECTED,
    CONFIRM_BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TARGET_CONSUMER_MODULES,
    build_betrayal_registry_consumer_refactor,
    load_betrayal_registry_consumer_refactor_records,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import build_strategy_evidence_registry

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    payload = build_betrayal_registry_consumer_refactor(log_dir=log_dir, now=NOW)

    assert payload["record_refactor_requested"] is False
    assert payload["refactor_recorded"] is False
    assert payload["refactor_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    payload = build_betrayal_registry_consumer_refactor(
        log_dir=log_dir,
        record_refactor=True,
        confirm_betrayal_registry_consumer_refactor="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_REGISTRY_CONSUMER_REFACTOR_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["refactor_recorded"] is False
    assert load_betrayal_registry_consumer_refactor_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_refactor_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_registry_consumer_refactor(
        log_dir=log_dir,
        record_refactor=True,
        confirm_betrayal_registry_consumer_refactor=CONFIRM_BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_registry_consumer_refactor_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_REGISTRY_CONSUMER_REFACTOR_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["refactor_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_REGISTRY_CONSUMER_REFACTOR"
    assert before_env == dict(os.environ)


def test_registry_missing_blocks_readiness_and_safe_fallback(tmp_path: Path) -> None:
    payload = build_betrayal_registry_consumer_refactor(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == BETRAYAL_REGISTRY_CONSUMER_REFACTOR_BLOCKED
    assert payload["input_summary"]["strategy_evidence_registry_found"] is False
    assert payload["registry_consumer_gap_report"]["registry_missing"] is True
    assert payload["registry_consumer_compatibility_report"]["registry_missing_would_block_readiness"] is True
    assert payload["refactor_recorded"] is False


def test_target_modules_report_registry_usage_inventory(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    payload = build_betrayal_registry_consumer_refactor(log_dir=log_dir, now=NOW)
    inventory = {row["module"]: row for row in payload["registry_consumer_inventory"]}

    for module_name in TARGET_CONSUMER_MODULES:
        row = inventory[module_name]
        assert row["consumes_betrayal_candidates_from_registry"] is True
        assert row["consumes_source_identity_requirements_from_registry"] is True
        assert row["consumes_safety_defaults_from_registry"] is True
        assert row["paper_only"] is True
        assert row["live_authorized"] is False


def test_registry_backed_requirements_and_candidates_are_reported(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    payload = build_betrayal_registry_consumer_refactor(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["registry_valid"] is True
    assert payload["registry_consumer_compatibility_report"]["modules_registry_backed"] == len(TARGET_CONSUMER_MODULES)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False


def test_remaining_hardcoded_lists_are_reported(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    payload = build_betrayal_registry_consumer_refactor(log_dir=log_dir, now=NOW)
    gap = payload["registry_consumer_gap_report"]

    assert gap["remaining_hardcoded_candidate_lists"]
    assert any(row["module"] == "betrayal_paper_matrix_context" for row in gap["remaining_hardcoded_candidate_lists"])


def test_all_safety_flags_remain_closed(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)
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
        payload = build_betrayal_registry_consumer_refactor(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
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
    _write_registry(log_dir)
    _write_registry_wiring(log_dir)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "betrayal-registry-consumer-refactor",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["input_summary"]["strategy_evidence_registry_found"] is True
    assert payload["refactor_recorded"] is False


def _write_registry(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = build_strategy_evidence_registry(log_dir=log_dir, now=NOW)
    path = log_dir / "strategy_evidence_registry.ndjson"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _write_registry_wiring(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_type": "REGISTRY_WIRING_BETRAYAL_SOURCE_FAMILY",
        "registry_backed_missing_field_report": {
            "missing_entry_mode_rows": 138,
            "missing_source_identity_rows": 141,
            "missing_direction_rows": 143,
            "resolver_ready_rows": 0,
        },
        "registry_wiring_gap_report": {
            "entry_mode_blocked": True,
            "betrayal_source_identity_blocked": True,
            "resolver_ready_rows": 0,
        },
        "wiring_status": "BETRAYAL_SOURCE_FAMILY_SOURCE_IDENTITY_BLOCKED",
        "safety": {"paper_live_separation_intact": True},
    }
    path = log_dir / "registry_wiring_betrayal_source_family.ndjson"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
