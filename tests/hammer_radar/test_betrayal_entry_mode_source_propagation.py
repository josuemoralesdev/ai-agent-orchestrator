import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_entry_mode_source_propagation import (
    BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED,
    BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_REJECTED,
    CONFIRM_BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDING_PHRASE,
    build_betrayal_entry_mode_source_propagation,
    build_entry_mode_propagated_rows_preview,
    build_lane_key_preview,
    load_betrayal_entry_mode_source_propagation_records,
    propagate_entry_mode_from_source,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import build_strategy_evidence_registry

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_source_propagation(log_dir=log_dir, now=NOW)

    assert payload["record_propagation_requested"] is False
    assert payload["propagation_recorded"] is False
    assert load_betrayal_entry_mode_source_propagation_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_source_propagation(
        log_dir=log_dir,
        record_propagation=True,
        confirm_betrayal_entry_mode_source_propagation="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["propagation_recorded"] is False
    assert load_betrayal_entry_mode_source_propagation_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_propagation_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_direction = (log_dir / "betrayal_direction_completion.ndjson").read_text(encoding="utf-8")

    payload = build_betrayal_entry_mode_source_propagation(
        log_dir=log_dir,
        record_propagation=True,
        confirm_betrayal_entry_mode_source_propagation=CONFIRM_BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_entry_mode_source_propagation_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION_RECORDED
    assert payload["propagation_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_ENTRY_MODE_SOURCE_PROPAGATION"
    assert (log_dir / "betrayal_direction_completion.ndjson").read_text(encoding="utf-8") == before_direction


def test_propagates_entry_mode_only_from_explicit_local_evidence() -> None:
    rows = build_entry_mode_propagated_rows_preview(
        betrayal_direction_completion={"direction_completed_rows_preview": [_direction_row(entry_mode=None)]},
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": [_entry_mode_row()]},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_renormalize_with_entry_mode={"renormalized_source_rows_preview": []},
        strategy_evidence_registry=_registry_record(),
        betrayal_shadow_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["entry_mode"] == "ladder_close_50_618"
    assert rows[0]["entry_mode_propagation_source"] == "explicit"
    assert rows[0]["resolver_ready_preview"] is True


def test_refuses_common_ladder_default_inference() -> None:
    rows = build_entry_mode_propagated_rows_preview(
        betrayal_direction_completion={"direction_completed_rows_preview": [_direction_row(entry_mode=None)]},
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_renormalize_with_entry_mode={"renormalized_source_rows_preview": []},
        strategy_evidence_registry=_registry_record(),
        betrayal_shadow_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["entry_mode"] is None
    assert rows[0]["entry_mode_propagation_source"] == "none"
    assert rows[0]["resolver_ready_preview"] is False


def test_refuses_candidate_label_inference() -> None:
    row = propagate_entry_mode_from_source(
        {"candidate": "ladder_close_50_618 betrayal candidate", "timeframe": "88m"},
        source_evidence_index={},
        registry_manifest=_registry_record()["registry_manifest"],
    )

    assert row.get("entry_mode") is None
    assert row["entry_mode_propagation_source"] == "none"


def test_builds_lane_key_preview_only_from_symbol_timeframe_direction_entry_mode() -> None:
    row = {"symbol": "BTCUSDT", "timeframe": "88m", "emitted_direction": "short", "entry_mode": "ladder_close_50_618"}

    assert build_lane_key_preview(row) == "BTCUSDT|88m|short|ladder_close_50_618"
    assert build_lane_key_preview({**row, "symbol": None}) is None
    assert build_lane_key_preview({**row, "timeframe": None}) is None
    assert build_lane_key_preview({**row, "emitted_direction": None}) is None
    assert build_lane_key_preview({**row, "entry_mode": None}) is None


def test_resolver_ready_requires_all_registry_fields() -> None:
    rows = build_entry_mode_propagated_rows_preview(
        betrayal_direction_completion={"direction_completed_rows_preview": [_direction_row(source_identity=None)]},
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": [_entry_mode_row()]},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_renormalize_with_entry_mode={"renormalized_source_rows_preview": []},
        strategy_evidence_registry=_registry_record(),
        betrayal_shadow_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["resolver_ready_preview"] is False
    assert rows[0]["schema_complete_preview"] is False
    assert "source_identity" in rows[0]["missing_required_fields"]


def test_no_append_of_normalized_rows(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    normalizer_path = log_dir / "betrayal_source_identity_normalizer.ndjson"
    normalizer_path.write_text(json.dumps({"normalized_source_rows_preview": []}) + "\n", encoding="utf-8")
    before = normalizer_path.read_text(encoding="utf-8")

    build_betrayal_entry_mode_source_propagation(log_dir=log_dir, now=NOW)

    assert normalizer_path.read_text(encoding="utf-8") == before


def test_all_rows_remain_paper_only_live_false_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_entry_mode_source_propagation(log_dir=log_dir, now=NOW)

    assert all(row["paper_only"] is True for row in payload["entry_mode_propagated_rows_preview"])
    assert all(row["live_authorized"] is False for row in payload["entry_mode_propagated_rows_preview"])
    assert all(row["promotion_allowed"] is False for row in payload["entry_mode_propagated_rows_preview"])
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

    payload = build_betrayal_entry_mode_source_propagation(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
    assert before_env == dict(os.environ)
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["ledger_rewritten"] is False
    assert payload["safety"]["destructive_write"] is False
    assert payload["safety"]["historical_ledger_rewritten"] is False


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
        payload = build_betrayal_entry_mode_source_propagation(log_dir=log_dir, now=NOW)

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
            "betrayal-entry-mode-source-propagation",
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
    _write_ndjson(log_dir / "betrayal_direction_completion.ndjson", {"direction_completed_rows_preview": [_direction_row(entry_mode=None)]})
    _write_ndjson(log_dir / "betrayal_renormalize_with_entry_mode.ndjson", {"renormalized_source_rows_preview": [_direction_row(entry_mode=None)]})
    _write_ndjson(log_dir / "betrayal_entry_mode_evidence_wiring.ndjson", {"entry_mode_evidence_rows": [_entry_mode_row()]})
    _write_ndjson(log_dir / "betrayal_source_identity_evidence_collector.ndjson", {"source_identity_evidence_rows": []})


def _direction_row(*, entry_mode: str | None = None, source_identity: str | None = "source_identity_88m_1") -> dict[str, object]:
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
        "emitted_signal_id_preview": "emitted_88m_1",
        "betrayal_event_identity": "betrayal|BTCUSDT|88m|signal_88m_1",
        "betrayal_event_identity_hash": "hash_88m_1",
        "outcome_windows": [1, 3, 5, 10, 21, 34, 55],
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _entry_mode_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "entry_mode_valid": True,
        "entry_mode_source": "explicit",
        "source_signal_id": "signal_88m_1",
        "timestamp": NOW.isoformat(),
        "paper_only": True,
        "live_authorized": False,
    }


def _registry_record() -> dict[str, object]:
    return build_strategy_evidence_registry(now=NOW)


def _write_ndjson(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
