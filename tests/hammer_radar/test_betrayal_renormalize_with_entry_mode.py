import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_renormalize_with_entry_mode import (
    BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED,
    BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_REJECTED,
    CONFIRM_BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDING_PHRASE,
    build_betrayal_renormalize_with_entry_mode,
    build_emitted_signal_id_preview,
    build_lane_key_preview,
    build_renormalized_source_rows_preview,
    load_betrayal_renormalize_with_entry_mode_records,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import build_strategy_evidence_registry

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_renormalize_with_entry_mode(log_dir=log_dir, now=NOW)

    assert payload["record_renormalization_requested"] is False
    assert payload["renormalization_recorded"] is False
    assert load_betrayal_renormalize_with_entry_mode_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_renormalize_with_entry_mode(
        log_dir=log_dir,
        record_renormalization=True,
        confirm_betrayal_renormalize_with_entry_mode="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["renormalization_recorded"] is False
    assert load_betrayal_renormalize_with_entry_mode_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_renormalization_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_normalizer = (log_dir / "betrayal_source_identity_normalizer.ndjson").read_text(encoding="utf-8")

    payload = build_betrayal_renormalize_with_entry_mode(
        log_dir=log_dir,
        record_renormalization=True,
        confirm_betrayal_renormalize_with_entry_mode=CONFIRM_BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_renormalize_with_entry_mode_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE_RECORDED
    assert payload["renormalization_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_RENORMALIZE_WITH_ENTRY_MODE"
    assert (log_dir / "betrayal_source_identity_normalizer.ndjson").read_text(encoding="utf-8") == before_normalizer


def test_joins_entry_mode_evidence_with_source_identity_evidence(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_renormalize_with_entry_mode(log_dir=log_dir, now=NOW)
    ready = [row for row in payload["renormalized_source_rows_preview"] if row["resolver_ready_preview"]]

    assert ready
    assert ready[0]["entry_mode"] == "ladder_close_50_618"
    assert ready[0]["source_identity"] == "source_identity_88m_1"
    assert "entry_mode:r225_entry_mode" in ready[0]["evidence_sources_used"]
    assert "source_identity:r224a_source_identity" in ready[0]["evidence_sources_used"]


def test_resolver_ready_requires_all_registry_fields(tmp_path: Path) -> None:
    registry = _registry_record()
    rows = build_renormalized_source_rows_preview(
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_source_identity_normalizer={"normalized_source_rows_preview": [{"candidate": "88m aggregate", "timeframe": "88m"}]},
        strategy_evidence_registry=registry,
        generated_at=NOW,
    )

    assert rows[0]["resolver_ready_preview"] is False
    assert rows[0]["schema_complete_preview"] is False
    assert "entry_mode" in rows[0]["missing_required_fields"]


def test_emitted_direction_must_equal_inverse_direction(tmp_path: Path) -> None:
    registry = _registry_record()
    bad = _normalizer_row()
    bad["entry_mode"] = "ladder_close_50_618"
    bad["source_identity"] = "source_identity_88m_1"
    bad["emitted_direction"] = "long"
    rows = build_renormalized_source_rows_preview(
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_source_identity_normalizer={"normalized_source_rows_preview": [bad]},
        strategy_evidence_registry=registry,
        generated_at=NOW,
    )

    assert rows[0]["resolver_ready_preview"] is False
    assert "emitted_direction_equals_inverse_direction" in rows[0]["missing_required_fields"]


def test_lane_key_preview_requires_emitted_direction_and_entry_mode() -> None:
    row = {"symbol": "BTCUSDT", "timeframe": "88m", "emitted_direction": "short", "entry_mode": "ladder_close_50_618"}

    assert build_lane_key_preview(row) == "BTCUSDT|88m|short|ladder_close_50_618"
    assert build_lane_key_preview({**row, "emitted_direction": None}) is None
    assert build_lane_key_preview({**row, "entry_mode": None}) is None


def test_emitted_signal_id_preview_requires_source_identity_and_emitted_direction() -> None:
    row = {"source_identity": "source_identity_88m_1", "emitted_direction": "short", "source_signal_timestamp": NOW.isoformat()}

    assert build_emitted_signal_id_preview(row)
    assert build_emitted_signal_id_preview({**row, "source_identity": None}) is None
    assert build_emitted_signal_id_preview({**row, "emitted_direction": None}) is None


def test_does_not_fabricate_common_ladder_mode(tmp_path: Path) -> None:
    registry = _registry_record()
    rows = build_renormalized_source_rows_preview(
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": [_source_identity_row(entry_mode=None)]},
        betrayal_source_identity_normalizer={"normalized_source_rows_preview": [_normalizer_row(entry_mode=None)]},
        strategy_evidence_registry=registry,
        generated_at=NOW,
    )

    assert all(row["entry_mode"] is None for row in rows)
    assert all(row["resolver_ready_preview"] is False for row in rows)


def test_all_rows_remain_paper_only_live_false_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_renormalize_with_entry_mode(log_dir=log_dir, now=NOW)

    assert all(row["paper_only"] is True for row in payload["renormalized_source_rows_preview"])
    assert all(row["live_authorized"] is False for row in payload["renormalized_source_rows_preview"])
    assert all(row["promotion_allowed"] is False for row in payload["renormalized_source_rows_preview"])
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

    payload = build_betrayal_renormalize_with_entry_mode(log_dir=log_dir, now=NOW)

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
        payload = build_betrayal_renormalize_with_entry_mode(log_dir=log_dir, now=NOW)

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
            "betrayal-renormalize-with-entry-mode",
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
        log_dir / "betrayal_source_identity_normalizer.ndjson",
        {"normalized_source_rows_preview": [_normalizer_row(entry_mode=None, source_identity=None)]},
    )
    _write_ndjson(
        log_dir / "betrayal_source_identity_evidence_collector.ndjson",
        {"source_identity_evidence_rows": [_source_identity_row(entry_mode=None)]},
    )
    _write_ndjson(
        log_dir / "betrayal_entry_mode_evidence_wiring.ndjson",
        {"entry_mode_evidence_rows": [_entry_mode_row()]},
    )


def _normalizer_row(*, entry_mode: str | None = None, source_identity: str | None = None) -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": entry_mode,
        "original_direction": "long",
        "inverse_direction": "short",
        "emitted_direction": "short",
        "source_identity": source_identity,
        "source_signal_id": "signal_88m_1",
        "source_signal_timestamp": NOW.isoformat(),
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _source_identity_row(*, entry_mode: str | None = None) -> dict[str, object]:
    return {
        **_normalizer_row(entry_mode=entry_mode, source_identity="source_identity_88m_1"),
        "emitted_signal_id_preview": "emitted_88m_1",
        "lane_key_preview": "BTCUSDT|88m|short|ladder_close_50_618" if entry_mode else None,
        "source": "r224a_source_identity",
    }


def _entry_mode_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "entry_mode_valid": True,
        "source_signal_id": "signal_88m_1",
        "timestamp": NOW.isoformat(),
        "source": "r225_entry_mode",
        "paper_only": True,
        "live_authorized": False,
    }


def _registry_record() -> dict[str, object]:
    return build_strategy_evidence_registry(now=NOW)


def _write_ndjson(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
