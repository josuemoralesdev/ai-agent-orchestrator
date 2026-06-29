from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter import (
    ADAPTER_IDS,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PARTIAL,
    SAFETY,
    SOURCE_LAB_ONLY,
    SOURCE_PENDING,
    SOURCE_WATCH_ONLY,
    build_strategy_lab_source_data_capture_adapter,
    load_strategy_lab_source_data_capture_adapter_records,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

REQUIRED_ROW_FIELDS = {
    "capture_adapter_id",
    "source_row_id",
    "lane_key",
    "timeframe",
    "side",
    "entry_mode",
    "source_gap_id",
    "capture_family",
    "capture_name",
    "capture_status",
    "source_inputs",
    "derived_capture_fields",
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


def test_builds_source_data_capture_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_source_data_capture_adapter_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["source_data_capture_status"] == PARTIAL
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_includes_all_seven_capture_adapters(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["capture_adapter_id"] for row in payload["capture_adapter_results"]] == list(ADAPTER_IDS)
    assert payload["capture_counts"]["implemented_capture_adapter_count"] == 7


def test_generates_normalized_source_data_rows(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["normalized_source_data_rows"]
    assert payload["capture_counts"]["normalized_source_data_row_count"] == len(payload["normalized_source_data_rows"])


def test_rows_include_required_schema_fields(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for row in payload["normalized_source_data_rows"]:
        assert REQUIRED_ROW_FIELDS <= set(row)
        assert row["used_existing_data_only"] is True
        assert row["synthetic_performance_created"] is False
        assert row["live_permission"] is False
        assert row["tiny_live_eligible_now"] is False
        assert row["promotion_event_written"] is False
        assert row["risk_contract_write_required"] is False
        assert row["observed_expansion_written"] is False
        assert row["scheduler_required"] is False


def test_exit_variant_comparison_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "exit_variant_comparison")

    assert rows
    assert "fixed_tp_sl_outcome" in {row["capture_name"] for row in rows}
    assert any("exit_outcome_source_missing" in row["blockers"] for row in rows)


def test_ma_wma_anchor_enrichment_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "ma_wma_anchor_enrichment")

    assert rows
    assert "wma200_value" in {row["capture_name"] for row in rows}
    assert any("anchor_timeseries_source_missing" in row["blockers"] for row in rows)


def test_review_ready_enrichment_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "review_ready_enrichment")

    assert rows
    assert "recent_sample_stability" in {row["capture_name"] for row in rows}
    assert "BTCUSDT|44m|short|ladder_382_50_618" in {row["lane_key"] for row in rows}


def test_short_capture_improvement_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "short_capture_improvement")

    assert rows
    assert {row["lane_key"] for row in rows} == {"BTCUSDT|8m|short|ladder_close_50_618"}
    assert "faster_capture_signal_delta" in {row["capture_name"] for row in rows}


def test_near_miss_variant_capture_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "near_miss_variant_capture")

    assert rows
    assert {row["lane_key"] for row in rows} == {
        "BTCUSDT|13m|long|ladder_close_50_618",
        "BTCUSDT|13m|short|ladder_close_50_618",
    }
    assert "timing_repair_observation" in {row["capture_name"] for row in rows}


def test_betrayal_inverse_source_chain_rows_generated_and_lab_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "betrayal_inverse_source_chain")

    assert rows
    assert all(row["capture_status"] == SOURCE_LAB_ONLY for row in rows)
    assert all(row["derived_capture_fields"]["lab_only"] is True for row in rows)
    assert all(row["derived_capture_fields"]["standard_55_policy_applies"] is False for row in rows)
    assert all(row["live_permission"] is False for row in rows)


def test_watch_88m_durability_rows_generated_and_watch_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "watch_88m_durability")

    assert rows
    assert {row["lane_key"] for row in rows} == {"BTCUSDT|88m|long|ladder_382_50_618"}
    assert all(row["capture_status"] == SOURCE_WATCH_ONLY for row in rows)
    assert all(row["derived_capture_fields"]["watch_only"] is True for row in rows)


def test_missing_source_data_is_marked_pending_not_invented(tmp_path: Path) -> None:
    rows = _build(tmp_path / "logs", write=False)["normalized_source_data_rows"]
    pending = [row for row in rows if row["capture_status"] == SOURCE_PENDING]

    assert pending
    assert all(row["synthetic_performance_created"] is False for row in pending)
    assert any("exit_outcome_source_missing" in row["blockers"] for row in pending)


def test_capture_counts_are_safe_zeroes(tmp_path: Path) -> None:
    counts = _build(tmp_path / "logs", write=False)["capture_counts"]

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
    payload = _build(tmp_path / "logs", write=False)

    assert payload["promotion_event_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["config_written"] is False
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
    assert payload["no_live_mutation_summary"]["no_scheduler_start"] is True


def test_required_safety_fields_match_shared_safety(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, value in SAFETY.items():
        assert payload["safety"][key] is value
        assert payload[key] is value


def test_remaining_capture_gaps_grouped(tmp_path: Path) -> None:
    gaps = _build(tmp_path / "logs", write=False)["remaining_capture_gaps"]["gaps"]
    by_gap = {row["gap_id"]: row for row in gaps}

    assert by_gap["exit_outcome_source_missing"]["row_count"] > 0
    assert by_gap["anchor_timeseries_source_missing"]["row_count"] > 0
    assert by_gap["mae_mfe_source_missing"]["row_count"] > 0
    assert by_gap["regime_split_source_missing"]["row_count"] > 0
    assert by_gap["betrayal_source_chain_source_missing"]["row_count"] > 0
    assert by_gap["watch_88m_durability_source_missing"]["row_count"] > 0


def test_recommended_paths_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["recommended_r332_path"]["phase"] == "R332 Strategy Lab Captured Source Data Merge Into Adapter Rows"
    assert payload["recommended_r330_path"]["phase"] == "R330 Human-Reviewed Observed Expansion Promotion Gate"
    assert "First Tiny Live remains" in payload["recommended_tiny_live_path"][0]


def test_inspect_route_works(tmp_path: Path) -> None:
    result = _run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            "logs/hammer_radar_forward",
            "strategy-lab-source-data-capture-adapter",
            "--no-write",
        ]
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["source_data_capture_status"] == PARTIAL


def test_operator_script_exists_and_prints_required_sections() -> None:
    script = Path("scripts/hammer_print_r331_strategy_lab_source_data_capture_adapter.sh")

    assert script.exists()
    result = _run(["bash", str(script)])
    output = result.stdout
    for section in (
        "R331 STRATEGY LAB SOURCE DATA CAPTURE ADAPTER",
        "CAPTURE COUNTS",
        "ADAPTER RESULT SUMMARY",
        "PENDING GAP SUMMARY",
        "BETRAYAL LAB-ONLY SOURCE-CHAIN PACKET",
        "WATCH-ONLY DURABILITY PACKET",
        "RECOMMENDED R332/R330",
        "SAFETY FLAGS",
    ):
        assert section in output


def _build(log_dir: Path, *, write: bool = True) -> dict:
    if not write:
        log_dir = Path("logs/hammer_radar_forward")
    return build_strategy_lab_source_data_capture_adapter(log_dir=log_dir, write=write, now=NOW)


def _rows(payload: dict, adapter_id: str) -> list[dict]:
    return [row for row in payload["normalized_source_data_rows"] if row["capture_adapter_id"] == adapter_id]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": "."}
    return subprocess.run(command, check=True, text=True, capture_output=True, env=env)
