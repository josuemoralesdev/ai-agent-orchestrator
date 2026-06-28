from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import (
    ADAPTER_IDS,
    EVENT_TYPE,
    LEDGER_FILENAME,
    READY,
    SAFETY,
    build_strategy_lab_evidence_adapter_pack,
    load_strategy_lab_evidence_adapter_pack_records,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)

REQUIRED_ROW_FIELDS = {
    "adapter_id",
    "row_id",
    "lane_key",
    "timeframe",
    "side",
    "entry_mode",
    "variant_family",
    "variant_name",
    "evidence_status",
    "source_chain",
    "input_fields",
    "derived_fields",
    "sample_count_source",
    "win_rate_source",
    "avg_pnl_source",
    "live_permission",
    "tiny_live_eligible_now",
    "promotion_event_written",
    "risk_contract_write_required",
    "scheduler_required",
    "blockers",
}


def test_builds_ready_evidence_adapter_pack(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_evidence_adapter_pack_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["evidence_adapter_pack_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_includes_all_seven_adapters(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["adapter_id"] for row in payload["adapter_results"]] == list(ADAPTER_IDS)
    assert payload["adapter_counts"]["implemented_adapter_count"] == 7


def test_generates_normalized_rows(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["normalized_evidence_rows"]
    assert payload["adapter_counts"]["normalized_evidence_row_count"] == len(payload["normalized_evidence_rows"])


def test_normalized_rows_include_required_schema_fields(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for row in payload["normalized_evidence_rows"]:
        assert REQUIRED_ROW_FIELDS <= set(row)
        assert row["live_permission"] is False
        assert row["tiny_live_eligible_now"] is False
        assert row["promotion_event_written"] is False
        assert row["risk_contract_write_required"] is False
        assert row["scheduler_required"] is False


def test_near_miss_13m_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "near_miss_13m")

    assert rows
    assert {row["lane_key"] for row in rows} == {
        "BTCUSDT|13m|long|ladder_close_50_618",
        "BTCUSDT|13m|short|ladder_close_50_618",
    }
    assert "timing_repair" in {row["variant_name"] for row in rows}


def test_capture_8m_short_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "capture_8m_short")

    assert rows
    assert {row["lane_key"] for row in rows} == {"BTCUSDT|8m|short|ladder_close_50_618"}
    assert "faster_capture" in {row["variant_name"] for row in rows}
    assert all(row["derived_fields"]["near_threshold"] is True for row in rows)


def test_ma_wma_anchor_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "ma_wma_anchor")

    assert rows
    assert "wma200_side" in {row["variant_name"] for row in rows}
    assert any("missing_raw_anchor_timeseries" in row["blockers"] for row in rows)


def test_exits_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "exits")

    assert rows
    assert "trailing_stop" in {row["variant_name"] for row in rows}
    assert any("missing_exit_outcome_comparison" in row["blockers"] for row in rows)


def test_betrayal_inverse_lab_rows_generated_and_lab_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "betrayal_inverse_lab")

    assert rows
    assert all(row["evidence_status"] == "LAB_ONLY" for row in rows)
    assert all(row["derived_fields"]["lab_only"] is True for row in rows)


def test_watch_88m_rows_generated_and_watch_only(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "watch_88m")

    assert rows
    assert {row["lane_key"] for row in rows} == {"BTCUSDT|88m|long|ladder_382_50_618"}
    assert all(row["evidence_status"] == "WATCH_ONLY" for row in rows)
    assert all(row["derived_fields"]["watch_only"] is True for row in rows)


def test_review_ready_enrichment_rows_generated(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "review_ready_enrichment")

    assert rows
    assert "recent_sample_stability" in {row["variant_name"] for row in rows}
    assert "BTCUSDT|44m|short|ladder_382_50_618" in {row["lane_key"] for row in rows}


def test_betrayal_standard_55_policy_false(tmp_path: Path) -> None:
    packet = _build(tmp_path / "logs", write=False)["betrayal_inverse_lab_adapter_packet"]
    rows = _rows(_build(tmp_path / "logs2", write=False), "betrayal_inverse_lab")

    assert packet["lab_only"] is True
    assert all(row["derived_fields"]["standard_55_policy_applies"] is False for row in rows)


def test_betrayal_source_chain_required(tmp_path: Path) -> None:
    rows = _rows(_build(tmp_path / "logs", write=False), "betrayal_inverse_lab")

    assert all(row["derived_fields"]["source_chain_required"] is True for row in rows)
    assert all(row["derived_fields"]["original_vs_inverse_required"] is True for row in rows)
    assert all(row["derived_fields"]["exact_risk_mapping_required"] is True for row in rows)
    assert all(row["derived_fields"]["stale_shadow_outcomes_forbidden"] is True for row in rows)


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE


def test_first_live_lane_change_allowed_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_live_lane_change_allowed"] is False


def test_live_permission_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["implemented_adapter_summary"]["live_permission_count"] == 0


def test_promotion_event_written_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["implemented_adapter_summary"]["promotion_event_written_count"] == 0
    assert payload["promotion_event_written"] is False


def test_risk_contract_write_required_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["implemented_adapter_summary"]["risk_contract_write_required_count"] == 0
    assert payload["risk_contract_config_mutated"] is False


def test_scheduler_required_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["implemented_adapter_summary"]["scheduler_required_count"] == 0
    assert payload["scheduler_started"] is False


def test_no_promotion_event_write(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["promotion_event_written"] is False
    assert payload["no_live_mutation_summary"]["no_promotion_event_write"] is True


def test_no_risk_contract_write(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["risk_contract_config_mutated"] is False
    assert payload["no_live_mutation_summary"]["no_risk_contract_write"] is True


def test_no_config_mutation(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["config_written"] is False
    assert payload["no_live_mutation_summary"]["no_config_or_env_mutation"] is True


def test_no_env_mutation(tmp_path: Path) -> None:
    env_before = dict(os.environ)
    payload = _build(tmp_path / "logs", write=False)

    assert dict(os.environ) == env_before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    arming_path = root / "configs/hammer_radar/autonomous_arming_state.json"
    before = arming_path.read_text(encoding="utf-8")
    payload = _build(tmp_path / "logs", write=False)

    assert arming_path.read_text(encoding="utf-8") == before
    assert payload["autonomous_arming_state_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_no_live_order(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["real_order_forbidden"] is True


def test_no_submit(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False


def test_no_telegram_send(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "strategy-lab-evidence-adapter-pack",
            "--no-write",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["evidence_adapter_pack_status"] == READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r328_strategy_lab_evidence_adapter_pack.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R328 STRATEGY LAB EVIDENCE ADAPTER IMPLEMENTATION PACK" in result.stdout
    assert "evidence_adapter_pack_status" in result.stdout
    assert "FIRST TINY LIVE LANE" in result.stdout
    assert "ADAPTER SUMMARY" in result.stdout
    assert "NORMALIZED EVIDENCE ROW COUNTS" in result.stdout
    assert "NEAR-MISS ADAPTER SUMMARY" in result.stdout
    assert "8M CAPTURE ADAPTER SUMMARY" in result.stdout
    assert "ANCHOR ADAPTER SUMMARY" in result.stdout
    assert "EXIT ADAPTER SUMMARY" in result.stdout
    assert "BETRAYAL LAB ADAPTER SUMMARY" in result.stdout
    assert "WATCH 88M ADAPTER SUMMARY" in result.stdout
    assert "REVIEW-READY ENRICHMENT SUMMARY" in result.stdout
    assert "REMAINING ADAPTER GAPS" in result.stdout
    assert "RECOMMENDED R329/R330" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    return build_strategy_lab_evidence_adapter_pack(
        log_dir=log_dir,
        now=NOW,
        write=write,
        candidate_feed_expansion_packet=_candidate_feed_expansion_packet(),
        promotion_review_packet=_promotion_review_packet(),
        batch_runner_packet=_batch_runner_packet(),
    )


def _rows(payload: dict[str, object], adapter_id: str) -> list[dict[str, object]]:
    return [row for row in payload["normalized_evidence_rows"] if row["adapter_id"] == adapter_id]


def _candidate_feed_expansion_packet() -> dict[str, object]:
    return {
        "candidate_feed_expansion_status": "STRATEGY_LAB_CANDIDATE_FEED_EXPANSION_READY",
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
    }


def _promotion_review_packet() -> dict[str, object]:
    return {
        "promotion_review_status": "STRATEGY_LAB_PROMOTION_REVIEW_READY",
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "review_ready_candidates": [
            _candidate("BTCUSDT|44m|short|ladder_382_50_618", 68, 69.12, 0.1186),
            _candidate("BTCUSDT|44m|short|ladder_close_50_618", 94, 61.7, 0.1081),
            _candidate("BTCUSDT|44m|short|ladder_22_44_22", 57, 68.42, 0.0836),
            _candidate("BTCUSDT|55m|long|ladder_close_50_618", 58, 58.62, 0.089),
            _candidate("BTCUSDT|55m|long|market_close", 59, 55.93, 0.0402),
        ],
        "needs_more_samples_candidates": [
            _candidate("BTCUSDT|13m|long|ladder_close_50_618", 324, 45.68, 0.0067),
            _candidate("BTCUSDT|13m|short|ladder_close_50_618", 317, 49.53, 0.0256),
            _candidate("BTCUSDT|8m|short|ladder_close_50_618", 564, 54.61, 0.022),
        ],
        "watch_only_candidates": [
            _candidate("BTCUSDT|88m|long|ladder_382_50_618", 45, 57.78, 0.07),
        ],
        "lab_only_candidates": ["BETRAYAL_INVERSE_LANES"],
    }


def _batch_runner_packet() -> dict[str, object]:
    evidence = {
        lane: {
            "sample_count": row["sample_count"],
            "win_rate_pct": row["win_rate_pct"],
            "avg_pnl_pct": row["avg_pnl_pct"],
            "evidence_status": "DIRECT_PAPER_EVIDENCE",
            "source_chain": ["test_strategy_lab_packet"],
        }
        for row in [
            *_promotion_review_packet()["review_ready_candidates"],
            *_promotion_review_packet()["needs_more_samples_candidates"],
            *_promotion_review_packet()["watch_only_candidates"],
        ]
        for lane in [row["lane_key"]]
    }
    return {
        "batch_runner_status": "STRATEGY_LAB_VARIANT_BATCH_RUNNER_READY",
        "tiny_live_baseline_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "lab_only_candidates": ["BETRAYAL_INVERSE_LANES"],
        "batch_results": [
            {"batch_id": "all_test_evidence", "current_evidence_snapshot": evidence},
        ],
    }


def _candidate(lane_key: str, sample_count: int, win_rate_pct: float, avg_pnl_pct: float) -> dict[str, object]:
    return {
        "lane_key": lane_key,
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "evidence_status": "DIRECT_PAPER_EVIDENCE",
        "recommended_decision": "PAPER_LAB_REVIEW",
    }
