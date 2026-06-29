from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge import (
    ADAPTER_BY_CAPTURE_ADAPTER,
    EVENT_TYPE,
    LEDGER_FILENAME,
    MERGED_LAB_ONLY,
    MERGED_PENDING_SOURCE_DATA,
    MERGED_READY,
    MERGED_UNMATCHED_ADAPTER_ROW,
    MERGED_UNMATCHED_SOURCE_ROW,
    MERGED_WATCH_ONLY,
    PARTIAL,
    SAFETY,
    build_strategy_lab_captured_source_data_merge,
    load_strategy_lab_captured_source_data_merge_records,
)
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import load_strategy_lab_evidence_adapter_pack_records
from src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet import (
    load_strategy_lab_adapter_output_batch_execution_packet_records,
)
from src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter import (
    load_strategy_lab_source_data_capture_adapter_records,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

REQUIRED_ROW_FIELDS = {
    "merge_row_id",
    "adapter_row_id",
    "source_row_id",
    "adapter_id",
    "capture_adapter_id",
    "lane_key",
    "timeframe",
    "side",
    "entry_mode",
    "variant_family",
    "variant_name",
    "evidence_status_from_adapter",
    "capture_status_from_source",
    "merged_status",
    "source_gap_id",
    "adapter_input_fields",
    "source_capture_fields",
    "source_chain",
    "used_existing_data_only",
    "synthetic_performance_created",
    "live_permission",
    "tiny_live_eligible_now",
    "promotion_event_written",
    "risk_contract_write_required",
    "observed_expansion_written",
    "scheduler_required",
    "blockers",
}


def test_builds_captured_source_data_merge_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    payload = _build(log_dir)
    records = load_strategy_lab_captured_source_data_merge_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["captured_source_data_merge_status"] == PARTIAL
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_reads_uses_r328_adapter_rows(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["merge_counts"]["adapter_rows_seen"] == 154
    assert payload["source_evidence_adapter_pack_status"] == "STRATEGY_LAB_EVIDENCE_ADAPTER_PACK_READY"


def test_reads_uses_r331_source_data_rows(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["merge_counts"]["source_rows_seen"] == 164
    assert payload["source_data_capture_status"] == "STRATEGY_LAB_SOURCE_DATA_CAPTURE_PARTIAL"


def test_produces_merged_adapter_rows(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["merged_adapter_rows"]
    assert payload["merge_counts"]["merged_row_count"] == len(payload["merged_adapter_rows"])


def test_merged_rows_include_required_schema_fields(tmp_path: Path) -> None:
    for row in _build(tmp_path / "logs", write=False)["merged_adapter_rows"]:
        assert REQUIRED_ROW_FIELDS <= set(row)
        assert row["used_existing_data_only"] is True
        assert row["synthetic_performance_created"] is False
        assert row["live_permission"] is False
        assert row["tiny_live_eligible_now"] is False
        assert row["promotion_event_written"] is False
        assert row["risk_contract_write_required"] is False
        assert row["observed_expansion_written"] is False
        assert row["scheduler_required"] is False


def test_includes_all_seven_adapter_capture_mappings(tmp_path: Path) -> None:
    summaries = _build(tmp_path / "logs", write=False)["adapter_merge_summaries"]

    assert {row["capture_adapter_id"]: row["adapter_id"] for row in summaries} == ADAPTER_BY_CAPTURE_ADAPTER


def test_status_rules_produce_merged_ready_for_source_ready_rows(tmp_path: Path) -> None:
    rows = _build(tmp_path / "logs", write=False)["merged_adapter_rows"]

    assert any(row["merged_status"] == MERGED_READY for row in rows)
    assert all(row["capture_status_from_source"] == "SOURCE_DATA_CAPTURE_READY" for row in rows if row["merged_status"] == MERGED_READY)


def test_status_rules_preserve_pending_source_data(tmp_path: Path) -> None:
    rows = _build(tmp_path / "logs", write=False)["merged_adapter_rows"]

    assert any(row["merged_status"] == MERGED_PENDING_SOURCE_DATA for row in rows)
    assert all(row["synthetic_performance_created"] is False for row in rows if row["merged_status"] == MERGED_PENDING_SOURCE_DATA)


def test_betrayal_rows_remain_lab_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "betrayal_inverse_source_chain")

    assert rows
    assert all(row["merged_status"] == MERGED_LAB_ONLY for row in rows)
    assert all(row["live_permission"] is False for row in rows)


def test_88m_rows_remain_watch_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "watch_88m_durability")

    assert rows
    assert all(row["merged_status"] == MERGED_WATCH_ONLY for row in rows)
    assert all(row["tiny_live_eligible_now"] is False for row in rows)


def test_unmatched_rows_are_represented_if_present(tmp_path: Path) -> None:
    evidence, batch, capture = _source_packets()
    adapter_row = dict(evidence["normalized_evidence_rows"][0])
    source_row = dict(capture["normalized_source_data_rows"][0])
    source_row["source_row_id"] = "r331|unmatched|source"
    source_row["lane_key"] = "BTCUSDT|1m|long|unmatched"
    source_row["source_inputs"] = {**source_row["source_inputs"], "source_adapter_id": "exits", "source_variant_name": "unmatched"}
    evidence = {**evidence, "normalized_evidence_rows": [adapter_row]}
    capture = {**capture, "normalized_source_data_rows": [source_row]}

    payload = build_strategy_lab_captured_source_data_merge(
        log_dir=tmp_path / "logs",
        write=False,
        now=NOW,
        evidence_adapter_pack=evidence,
        adapter_output_batch_execution_packet=batch,
        source_data_capture_adapter=capture,
    )
    statuses = {row["merged_status"] for row in payload["merged_adapter_rows"]}

    assert MERGED_UNMATCHED_SOURCE_ROW in statuses
    assert MERGED_UNMATCHED_ADAPTER_ROW in statuses
    assert payload["merge_counts"]["unmatched_source_rows"] == 1
    assert payload["merge_counts"]["unmatched_adapter_rows"] == 1


def test_required_summaries_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["ready_merge_summary"]["ready_row_count"] == 18
    assert payload["pending_merge_summary"]["pending_row_count"] == 135
    assert payload["lab_only_merge_summary"]["betrayal_inverse_remains_lab_only"] is True
    assert payload["watch_only_merge_summary"]["watch_88m_remains_watch_only"] is True


def test_zero_mutation_counts(tmp_path: Path) -> None:
    counts = _build(tmp_path / "logs", write=False)["merge_counts"]

    assert counts["synthetic_performance_created_count"] == 0
    assert counts["live_permission_count"] == 0
    assert counts["promotion_event_written_count"] == 0
    assert counts["risk_contract_write_required_count"] == 0
    assert counts["observed_expansion_written_count"] == 0
    assert counts["scheduler_required_count"] == 0


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE
    assert payload["first_live_lane_change_allowed"] is False


def test_no_mutation_safety_flags(tmp_path: Path) -> None:
    env_before = dict(os.environ)
    payload = _build(tmp_path / "logs", write=False)

    assert dict(os.environ) == env_before
    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
    assert payload["promotion_event_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["config_written"] is False
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    result = _run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "strategy-lab-captured-source-data-merge",
            "--no-write",
        ]
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["captured_source_data_merge_status"] == PARTIAL


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r332_strategy_lab_captured_source_data_merge.sh"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    for section in (
        "R332 STRATEGY LAB CAPTURED SOURCE DATA MERGE INTO ADAPTER ROWS",
        "captured_source_data_merge_status",
        "FIRST TINY LIVE LANE",
        "MERGE COUNTS",
        "ADAPTER MERGE SUMMARIES",
        "READY MERGE SUMMARY",
        "PENDING MERGE SUMMARY",
        "BETRAYAL LAB-ONLY SUMMARY",
        "WATCH-ONLY SUMMARY",
        "RECOMMENDED R333/R330",
        "SAFETY FLAGS",
    ):
        assert section in result.stdout


def test_r331_r329_r328_r314_tests_remain_compatible() -> None:
    result = _run(
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            "tests/hammer_radar/test_strategy_lab_source_data_capture_adapter.py",
            "tests/hammer_radar/test_strategy_lab_adapter_output_batch_execution_packet.py",
            "tests/hammer_radar/test_strategy_lab_evidence_adapter_pack.py",
            "tests/hammer_radar/test_strategy_lab_candidate_feed_expansion.py",
            "tests/hammer_radar/test_multi_lane_observation_health_panel.py",
            "-q",
        ]
    )

    assert "failed" not in result.stdout.lower()


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    evidence, batch, capture = _source_packets()
    return build_strategy_lab_captured_source_data_merge(
        log_dir=log_dir,
        write=write,
        now=NOW,
        evidence_adapter_pack=evidence,
        adapter_output_batch_execution_packet=batch,
        source_data_capture_adapter=capture,
    )


def _source_packets() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    log_dir = Path("logs/hammer_radar_forward")
    evidence = load_strategy_lab_evidence_adapter_pack_records(log_dir=log_dir, limit=1)[-1]
    batch = load_strategy_lab_adapter_output_batch_execution_packet_records(log_dir=log_dir, limit=1)[-1]
    capture = load_strategy_lab_source_data_capture_adapter_records(log_dir=log_dir, limit=1)[-1]
    return evidence, batch, capture


def _rows(payload: dict[str, object], capture_adapter_id: str) -> list[dict[str, object]]:
    return [row for row in payload["merged_adapter_rows"] if row["capture_adapter_id"] == capture_adapter_id]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        command,
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
