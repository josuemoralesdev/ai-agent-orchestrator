from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_upstream_emitter_entry_mode_contract import (
    BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED,
    BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_REJECTED,
    CONFIRM_BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDING_PHRASE,
    build_betrayal_lane_key,
    build_betrayal_upstream_contract_row,
    build_betrayal_upstream_emitter_entry_mode_contract,
    get_betrayal_upstream_required_fields,
    load_betrayal_upstream_contract_records,
    validate_betrayal_upstream_contract_row,
    validate_entry_mode_for_upstream_contract,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import build_strategy_evidence_registry

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_upstream_emitter_entry_mode_contract(log_dir=log_dir, now=NOW)

    assert payload["record_contract_requested"] is False
    assert payload["contract_recorded"] is False
    assert load_betrayal_upstream_contract_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_upstream_emitter_entry_mode_contract(
        log_dir=log_dir,
        record_contract=True,
        confirm_betrayal_upstream_emitter_entry_mode_contract="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["contract_recorded"] is False
    assert load_betrayal_upstream_contract_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_contract_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_propagation = (log_dir / "betrayal_entry_mode_source_propagation.ndjson").read_text(encoding="utf-8")

    payload = build_betrayal_upstream_emitter_entry_mode_contract(
        log_dir=log_dir,
        record_contract=True,
        confirm_betrayal_upstream_emitter_entry_mode_contract=(
            CONFIRM_BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDING_PHRASE
        ),
        now=NOW,
    )

    records = load_betrayal_upstream_contract_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT_RECORDED
    assert payload["contract_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_UPSTREAM_EMITTER_ENTRY_MODE_CONTRACT"
    assert (log_dir / "betrayal_entry_mode_source_propagation.ndjson").read_text(encoding="utf-8") == before_propagation


def test_contract_requires_entry_mode_and_lane_key() -> None:
    required = get_betrayal_upstream_required_fields()
    assert "entry_mode" in required
    assert "lane_key" in required

    row = _contract_row()
    row.pop("entry_mode")
    row.pop("lane_key")
    validation = validate_betrayal_upstream_contract_row(row, registry_manifest=_registry_manifest())

    assert validation["valid"] is False
    assert "entry_mode" in validation["missing_required_fields"]
    assert "lane_key" in validation["missing_required_fields"]


def test_entry_mode_must_exist_in_registry_and_rejects_placeholders() -> None:
    manifest = _registry_manifest()

    assert validate_entry_mode_for_upstream_contract("ladder_close_50_618", registry_manifest=manifest)["valid"] is True
    assert validate_entry_mode_for_upstream_contract("not_registered", registry_manifest=manifest)["valid"] is False
    assert validate_entry_mode_for_upstream_contract("unknown", registry_manifest=manifest)["valid"] is False
    assert validate_entry_mode_for_upstream_contract("entry_unknown", registry_manifest=manifest)["valid"] is False


def test_refuses_common_default_candidate_label_and_timeframe_inference() -> None:
    manifest = _registry_manifest()

    for inference_source in ("common_default", "candidate_label", "timeframe_only"):
        validation = validate_entry_mode_for_upstream_contract(
            "ladder_close_50_618",
            registry_manifest=manifest,
            inference_source=inference_source,
        )
        assert validation["valid"] is False
        assert validation["rejection_reason"] == f"entry_mode_inference_forbidden:{inference_source}"


def test_builds_lane_key_only_from_symbol_timeframe_emitted_direction_entry_mode() -> None:
    assert (
        build_betrayal_lane_key(
            symbol="BTCUSDT",
            timeframe="88m",
            emitted_direction="short",
            entry_mode="ladder_close_50_618",
        )
        == "BTCUSDT|88m|short|ladder_close_50_618"
    )
    assert build_betrayal_lane_key(symbol=None, timeframe="88m", emitted_direction="short", entry_mode="ladder_close_50_618") is None
    assert build_betrayal_lane_key(symbol="BTCUSDT", timeframe=None, emitted_direction="short", entry_mode="ladder_close_50_618") is None
    assert build_betrayal_lane_key(symbol="BTCUSDT", timeframe="88m", emitted_direction=None, entry_mode="ladder_close_50_618") is None
    assert build_betrayal_lane_key(symbol="BTCUSDT", timeframe="88m", emitted_direction="short", entry_mode=None) is None


def test_emitted_direction_must_equal_inverse_direction_for_inverse_rows() -> None:
    validation = validate_betrayal_upstream_contract_row(
        {**_contract_row(), "emitted_direction": "long", "lane_key": "BTCUSDT|88m|long|ladder_close_50_618"},
        registry_manifest=_registry_manifest(),
    )

    assert validation["valid"] is False
    assert "emitted_direction_equals_inverse_direction" in validation["missing_required_fields"]


def test_build_contract_row_sets_future_paper_only_fields_complete() -> None:
    row = build_betrayal_upstream_contract_row(_raw_future_row(), registry_manifest=_registry_manifest())

    assert row["contract_validation"]["valid"] is True
    assert row["lane_key"] == "BTCUSDT|88m|short|ladder_close_50_618"
    assert row["emitted_direction"] == row["inverse_direction"]
    assert row["paper_only"] is True
    assert row["live_authorized"] is False
    assert row["promotion_allowed"] is False
    assert row["emitted_signal_id"].startswith("betrayal_emitted|")


def test_historical_rows_are_not_rewritten_and_no_normalized_rows_appended(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    normalizer_path = log_dir / "betrayal_source_identity_normalizer.ndjson"
    normalizer_path.write_text(json.dumps({"normalized_source_rows_preview": []}) + "\n", encoding="utf-8")
    before_normalizer = normalizer_path.read_text(encoding="utf-8")
    before_propagation = (log_dir / "betrayal_entry_mode_source_propagation.ndjson").read_text(encoding="utf-8")

    payload = build_betrayal_upstream_emitter_entry_mode_contract(log_dir=log_dir, now=NOW)

    assert normalizer_path.read_text(encoding="utf-8") == before_normalizer
    assert (log_dir / "betrayal_entry_mode_source_propagation.ndjson").read_text(encoding="utf-8") == before_propagation
    assert payload["existing_row_compatibility_report"]["historical_rows_rewritten"] is False
    assert payload["existing_row_compatibility_report"]["historical_resolver_ready_rows_created"] == 0
    assert payload["safety"]["normalized_rows_appended"] is False


def test_all_rows_remain_paper_only_live_false_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_upstream_emitter_entry_mode_contract(log_dir=log_dir, now=NOW)

    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_mutation_or_destructive_ledger_rewrite(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    payload = build_betrayal_upstream_emitter_entry_mode_contract(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_env == dict(os.environ)
    for key in (
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
    ):
        assert payload["safety"][key] is False


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
        payload = build_betrayal_upstream_emitter_entry_mode_contract(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key, value in payload["safety"].items():
        if key in {"paper_live_separation_intact", "future_contract_only"}:
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
            "betrayal-upstream-emitter-entry-mode-contract",
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
    _write_ndjson(log_dir / "strategy_evidence_registry.ndjson", _registry_record())
    _write_ndjson(
        log_dir / "betrayal_entry_mode_source_propagation.ndjson",
        {
            "source_propagation_summary": {
                "rows_reviewed": 3,
                "resolver_ready_preview_rows": 0,
                "rows_with_entry_mode_after": 1,
                "rows_with_lane_key_preview": 1,
            },
            "source_propagation_gap_report": {
                "missing_entry_mode_rows": 2,
                "missing_lane_key_rows": 2,
                "resolver_ready_preview_rows": 0,
            },
        },
    )


def _write_ndjson(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _registry_record() -> dict[str, object]:
    return build_strategy_evidence_registry(now=NOW)


def _registry_manifest() -> dict[str, object]:
    return _registry_record()["registry_manifest"]


def _raw_future_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "original_direction": "long",
        "inverse_direction": "short",
        "emitted_direction": "short",
        "source_identity": "source_identity_88m_1",
        "source_signal_id": "signal_88m_1",
        "source_signal_timestamp": NOW.isoformat(),
    }


def _contract_row() -> dict[str, object]:
    row = build_betrayal_upstream_contract_row(_raw_future_row(), registry_manifest=_registry_manifest())
    row.pop("entry_mode_validation", None)
    row.pop("contract_validation", None)
    return row
