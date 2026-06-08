import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_direction_completion import (
    BETRAYAL_DIRECTION_COMPLETION_RECORDED,
    BETRAYAL_DIRECTION_COMPLETION_REJECTED,
    CONFIRM_BETRAYAL_DIRECTION_COMPLETION_RECORDING_PHRASE,
    build_betrayal_direction_completion,
    build_direction_completed_rows_preview,
    complete_direction_fields,
    load_betrayal_direction_completion_records,
)
from src.app.hammer_radar.operator.strategy_evidence_registry import build_strategy_evidence_registry

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_completion(log_dir=log_dir, now=NOW)

    assert payload["record_completion_requested"] is False
    assert payload["completion_recorded"] is False
    assert load_betrayal_direction_completion_records(log_dir=log_dir, limit=0) == []


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_completion(
        log_dir=log_dir,
        record_completion=True,
        confirm_betrayal_direction_completion="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_DIRECTION_COMPLETION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["completion_recorded"] is False
    assert load_betrayal_direction_completion_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_completion_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_renormalization = (log_dir / "betrayal_renormalize_with_entry_mode.ndjson").read_text(encoding="utf-8")

    payload = build_betrayal_direction_completion(
        log_dir=log_dir,
        record_completion=True,
        confirm_betrayal_direction_completion=CONFIRM_BETRAYAL_DIRECTION_COMPLETION_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_direction_completion_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_DIRECTION_COMPLETION_RECORDED
    assert payload["completion_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_DIRECTION_COMPLETION"
    assert (log_dir / "betrayal_renormalize_with_entry_mode.ndjson").read_text(encoding="utf-8") == before_renormalization


def test_completes_inverse_direction_only_from_explicit_or_original_direction_evidence() -> None:
    rows = build_direction_completed_rows_preview(
        betrayal_renormalize_with_entry_mode={"renormalized_source_rows_preview": [_renormalized_row()]},
        betrayal_direction_split_resolver={"direction_split_resolution_rows": [_direction_split_row()]},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        strategy_evidence_registry=_registry_record(),
        betrayal_shadow_outcomes=[],
        betrayal_true_paper_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["original_direction"] == "long"
    assert rows[0]["inverse_direction"] == "short"
    assert "inverse_direction:direction_split_resolver" in rows[0]["direction_completion_sources_used"]


def test_emitted_direction_equals_inverse_direction_for_betrayal_inverse_rows() -> None:
    row = complete_direction_fields(
        {
            "candidate": "88m aggregate",
            "source_type": "betrayal_source_emitter",
            "original_direction": "long",
            "inverse_direction": "short",
        }
    )

    assert row["emitted_direction"] == "short"


def test_refuses_aggregate_label_direction_inference() -> None:
    row = complete_direction_fields({"candidate": "short aggregate", "source_type": "betrayal_source_emitter"})

    assert row.get("original_direction") is None
    assert row.get("inverse_direction") is None
    assert row.get("emitted_direction") is None


def test_refuses_emitted_direction_if_inverse_direction_missing() -> None:
    row = complete_direction_fields({"candidate": "88m aggregate", "source_type": "betrayal_source_emitter"})

    assert row.get("emitted_direction") is None


def test_resolver_ready_requires_all_registry_fields() -> None:
    rows = build_direction_completed_rows_preview(
        betrayal_renormalize_with_entry_mode={"renormalized_source_rows_preview": [{"candidate": "88m aggregate", "timeframe": "88m"}]},
        betrayal_direction_split_resolver={"direction_split_resolution_rows": []},
        betrayal_source_identity_evidence_collector={"source_identity_evidence_rows": []},
        betrayal_entry_mode_evidence_wiring={"entry_mode_evidence_rows": []},
        strategy_evidence_registry=_registry_record(),
        betrayal_shadow_outcomes=[],
        betrayal_true_paper_outcomes=[],
        betrayal_paper_signals=[],
        generated_at=NOW,
    )

    assert rows[0]["resolver_ready_preview"] is False
    assert rows[0]["schema_complete_preview"] is False
    assert "entry_mode" in rows[0]["missing_required_fields"]


def test_no_append_of_normalized_rows(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    normalizer_path = log_dir / "betrayal_source_identity_normalizer.ndjson"
    normalizer_path.write_text(json.dumps({"normalized_source_rows_preview": []}) + "\n", encoding="utf-8")
    before = normalizer_path.read_text(encoding="utf-8")

    build_betrayal_direction_completion(log_dir=log_dir, now=NOW)

    assert normalizer_path.read_text(encoding="utf-8") == before


def test_all_rows_remain_paper_only_live_false_no_betrayal_promotion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_direction_completion(log_dir=log_dir, now=NOW)

    assert all(row["paper_only"] is True for row in payload["direction_completed_rows_preview"])
    assert all(row["live_authorized"] is False for row in payload["direction_completed_rows_preview"])
    assert all(row["promotion_allowed"] is False for row in payload["direction_completed_rows_preview"])
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

    payload = build_betrayal_direction_completion(log_dir=log_dir, now=NOW)

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
        payload = build_betrayal_direction_completion(log_dir=log_dir, now=NOW)

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
            "betrayal-direction-completion",
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
    _write_ndjson(log_dir / "betrayal_renormalize_with_entry_mode.ndjson", {"renormalized_source_rows_preview": [_renormalized_row()]})
    _write_ndjson(log_dir / "betrayal_direction_split_resolver.ndjson", {"direction_split_resolution_rows": [_direction_split_row()]})
    _write_ndjson(log_dir / "betrayal_source_identity_evidence_collector.ndjson", {"source_identity_evidence_rows": [_source_identity_row()]})
    _write_ndjson(log_dir / "betrayal_entry_mode_evidence_wiring.ndjson", {"entry_mode_evidence_rows": [_entry_mode_row()]})


def _renormalized_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "original_direction": None,
        "inverse_direction": None,
        "emitted_direction": None,
        "source_identity": "source_identity_88m_1",
        "source_signal_id": "BTCUSDT|88m|long|2026-06-08T10:00:00+00:00",
        "source_signal_timestamp": "2026-06-08T10:00:00+00:00",
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _direction_split_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "original_direction": "long",
        "inverse_direction": "short",
        "source_signal_id": "BTCUSDT|88m|long|2026-06-08T10:00:00+00:00",
        "signal_timestamp": "2026-06-08T10:00:00+00:00",
        "source": "direction_split_resolver",
        "paper_only": True,
        "live_authorized": False,
    }


def _source_identity_row() -> dict[str, object]:
    return {
        **_renormalized_row(),
        "original_direction": "long",
        "inverse_direction": "short",
        "emitted_direction": "short",
        "emitted_signal_id_preview": "emitted_88m_1",
        "lane_key_preview": "BTCUSDT|88m|short|ladder_close_50_618",
        "source": "source_identity_evidence",
    }


def _entry_mode_row() -> dict[str, object]:
    return {
        "candidate": "88m aggregate",
        "symbol": "BTCUSDT",
        "timeframe": "88m",
        "entry_mode": "ladder_close_50_618",
        "entry_mode_valid": True,
        "source_signal_id": "BTCUSDT|88m|long|2026-06-08T10:00:00+00:00",
        "timestamp": "2026-06-08T10:00:00+00:00",
        "source": "entry_mode_evidence",
        "paper_only": True,
        "live_authorized": False,
    }


def _registry_record() -> dict[str, object]:
    return build_strategy_evidence_registry(now=NOW)


def _write_ndjson(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
