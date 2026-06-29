from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet import (
    ADAPTER_IDS,
    EVENT_TYPE,
    LEDGER_FILENAME,
    READY,
    SAFETY,
    build_strategy_lab_adapter_output_batch_execution_packet,
    load_strategy_lab_adapter_output_batch_execution_packet_records,
)
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack import build_strategy_lab_evidence_adapter_pack

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def test_builds_ready_adapter_batch_execution_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_adapter_output_batch_execution_packet_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["adapter_batch_execution_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_reads_uses_r328_normalized_row_summary(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    summary = payload["input_row_summary"]

    assert summary["normalized_evidence_row_count"] == 154
    assert summary["ready_rows"] == 20
    assert summary["rows_needing_source_data"] == 124
    assert summary["lab_only_rows"] == 5
    assert summary["watch_only_rows"] == 5


def test_includes_all_adapter_family_summaries(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["adapter_id"] for row in payload["adapter_family_summaries"]] == list(ADAPTER_IDS)


def test_includes_ready_row_rankings(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["ready_row_rankings"]
    assert payload["ready_row_rankings"][0]["rank"] == 1


def test_includes_source_data_gap_rankings(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["source_data_gap_rankings"]
    assert payload["source_data_gap_rankings"][0]["source_data_gap_score"] >= payload["source_data_gap_rankings"][-1]["source_data_gap_score"]


def test_includes_adapter_usefulness_ranking(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["adapter_usefulness_ranking"]
    assert all(row["adapter_id"] != "betrayal_inverse_lab" for row in payload["adapter_usefulness_ranking"])


def test_includes_capture_priorities(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    priorities = [row["adapter"] for row in payload["recommended_capture_priorities"]]
    assert priorities == [
        "short_capture_improvement_adapter",
        "exit_variant_comparison_adapter",
        "ma_wma_anchor_enrichment_adapter",
        "review_ready_enrichment_adapter",
        "near_miss_variant_capture_adapter",
        "betrayal_inverse_source_chain_adapter",
        "watch_88m_durability_adapter",
    ]


def test_capture_8m_short_ranked_high(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    ranks = {row["adapter_id"]: row["rank"] for row in payload["adapter_usefulness_ranking"]}

    assert ranks["capture_8m_short"] <= 3


def test_near_miss_13m_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert _family(payload, "near_miss_13m")["ready_rows"] == 10


def test_review_ready_enrichment_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert _family(payload, "review_ready_enrichment")["ready_rows"] == 5


def test_exits_gap_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert any(row["adapter_id"] == "exits" and row["gap_id"] == "missing_exit_outcome_comparison" for row in payload["source_data_gap_rankings"])


def test_ma_wma_anchor_gap_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert any(row["adapter_id"] == "ma_wma_anchor" and row["gap_id"] == "missing_raw_anchor_timeseries" for row in payload["source_data_gap_rankings"])


def test_betrayal_lab_only_summary_included(tmp_path: Path) -> None:
    summary = _build(tmp_path / "logs", write=False)["betrayal_inverse_lab_only_summary"]

    assert summary["lab_only"] is True
    assert summary["source_chain_required"] is True
    assert summary["recommended_next_action"] == "CAPTURE_LAB_ONLY_SOURCE_CHAIN_DATA"


def test_betrayal_excluded_from_standard_ranking(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert "betrayal_inverse_lab" not in {row["adapter_id"] for row in payload["adapter_usefulness_ranking"]}
    assert payload["betrayal_inverse_lab_only_summary"]["excluded_from_standard_ranking"] is True


def test_watch_88m_remains_watch_only(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert _family(payload, "watch_88m")["readiness_status"] == "WATCH_ONLY_REVIEW"
    assert payload["watch_only_summary"]["watch_only"] is True


def test_observed_expansion_review_inputs_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["lane_key"] for row in payload["recommended_observed_expansion_review_inputs"]] == [
        "BTCUSDT|44m|short|ladder_382_50_618",
        "BTCUSDT|44m|short|ladder_close_50_618",
        "BTCUSDT|44m|short|ladder_22_44_22",
        "BTCUSDT|55m|long|ladder_close_50_618",
        "BTCUSDT|55m|long|market_close",
    ]


def test_observed_expansion_review_inputs_have_live_permission_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert all(row["review_scope"] == "observed expansion review only" for row in payload["recommended_observed_expansion_review_inputs"])
    assert all(row["human_review_required"] is True for row in payload["recommended_observed_expansion_review_inputs"])
    assert all(row["live_permission"] is False for row in payload["recommended_observed_expansion_review_inputs"])


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE


def test_first_live_lane_change_allowed_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_live_lane_change_allowed"] is False


def test_live_permission_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["input_row_summary"]["live_permission_count"] == 0


def test_promotion_event_written_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["input_row_summary"]["promotion_event_written_count"] == 0
    assert payload["promotion_event_written"] is False


def test_risk_contract_write_required_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["input_row_summary"]["risk_contract_write_required_count"] == 0
    assert payload["risk_contract_config_mutated"] is False


def test_scheduler_required_count_zero(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["input_row_summary"]["scheduler_required_count"] == 0
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
            "strategy-lab-adapter-output-batch-execution-packet",
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
    assert payload["adapter_batch_execution_status"] == READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r329_strategy_lab_adapter_output_batch_execution_packet.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R329 STRATEGY LAB ADAPTER OUTPUT BATCH EXECUTION PACKET" in result.stdout
    assert "adapter_batch_execution_status" in result.stdout
    assert "FIRST TINY LIVE LANE" in result.stdout
    assert "INPUT ROW SUMMARY" in result.stdout
    assert "ADAPTER USEFULNESS RANKING" in result.stdout
    assert "SOURCE-DATA GAP RANKING" in result.stdout
    assert "RECOMMENDED CAPTURE PRIORITIES" in result.stdout
    assert "OBSERVED EXPANSION REVIEW INPUTS" in result.stdout
    assert "BETRAYAL LAB-ONLY SUMMARY" in result.stdout
    assert "WATCH-ONLY SUMMARY" in result.stdout
    assert "RECOMMENDED R330/R331" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def test_r328_r326_r325_r314_tests_remain_compatible() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            "tests/hammer_radar/test_strategy_lab_evidence_adapter_pack.py",
            "tests/hammer_radar/test_strategy_lab_candidate_feed_expansion.py",
            "tests/hammer_radar/test_strategy_lab_promotion_review_packet.py",
            "tests/hammer_radar/test_strategy_lab_variant_batch_runner.py",
            "tests/hammer_radar/test_strategy_lab_expansion_surface_map.py",
            "-q",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "failed" not in result.stdout.lower()


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    r328 = build_strategy_lab_evidence_adapter_pack(
        log_dir=log_dir,
        now=NOW,
        write=False,
        candidate_feed_expansion_packet=_candidate_feed_expansion_packet(),
        promotion_review_packet=_promotion_review_packet(),
        batch_runner_packet=_batch_runner_packet(),
    )
    return build_strategy_lab_adapter_output_batch_execution_packet(
        log_dir=log_dir,
        now=NOW,
        write=write,
        evidence_adapter_pack=r328,
    )


def _family(payload: dict[str, object], adapter_id: str) -> dict[str, object]:
    for row in payload["adapter_family_summaries"]:
        if row["adapter_id"] == adapter_id:
            return row
    raise AssertionError(f"missing adapter family {adapter_id}")


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
