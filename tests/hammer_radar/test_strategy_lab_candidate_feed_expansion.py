from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import (
    BASELINE_LANE,
    EVENT_TYPE,
    FEED_IDS,
    LEDGER_FILENAME,
    MISSING_ADAPTERS,
    READY,
    SAFETY,
    build_strategy_lab_candidate_feed_expansion,
    load_strategy_lab_candidate_feed_expansion_records,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def test_builds_ready_candidate_feed_expansion_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_candidate_feed_expansion_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["candidate_feed_expansion_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_includes_all_required_feeds(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["feed_id"] for row in payload["feed_expansion_packets"]] == list(FEED_IDS)
    assert payload["feed_counts"]["feed_packet_count"] == 7


def test_includes_near_miss_13m_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "near_miss_13m")

    assert packet["candidate_lanes"] == [
        "BTCUSDT|13m|long|ladder_close_50_618",
        "BTCUSDT|13m|short|ladder_close_50_618",
    ]
    assert "timing repair" in packet["feed_dimensions"]
    assert packet["recommended_next_action"] == "add paper/lab capture adapters for variants"


def test_includes_capture_8m_short_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "capture_8m_short")

    assert packet["candidate_lanes"] == ["BTCUSDT|8m|short|ladder_close_50_618"]
    assert "faster capture" in packet["feed_dimensions"]
    assert packet["recommended_next_action"] == "add capture-improvement evidence adapter"


def test_includes_ma_wma_anchor_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "ma_wma_anchor")

    assert "WMA200 support/resistance anchor" in packet["feed_dimensions"]
    assert "MA200 support/resistance anchor" in packet["feed_dimensions"]
    assert "golden-pocket + anchor confluence" in packet["feed_dimensions"]


def test_includes_exits_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "exits")

    assert "fixed TP/SL" in packet["feed_dimensions"]
    assert "trailing" in packet["feed_dimensions"]
    assert "invalidation tightening" in packet["feed_dimensions"]


def test_includes_betrayal_inverse_lab_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "betrayal_inverse_lab")

    assert packet["candidate_lanes"] == ["BETRAYAL_INVERSE_LANES"]
    assert packet["recommended_next_action"] == "source-chain and original-vs-inverse capture adapter only"


def test_includes_watch_88m_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "watch_88m")

    assert packet["candidate_lanes"] == ["BTCUSDT|88m|long|ladder_382_50_618"]
    assert "durability" in packet["feed_dimensions"]
    assert packet["recommended_next_action"] == "keep watch-only and deepen evidence"


def test_includes_review_ready_enrichment_feed(tmp_path: Path) -> None:
    packet = _feed(_build(tmp_path / "logs", write=False), "review_ready_enrichment")

    assert "BTCUSDT|44m|short|ladder_382_50_618" in packet["candidate_lanes"]
    assert "stability over recent samples" in packet["feed_dimensions"]
    assert packet["recommended_next_action"] == "enrich evidence before observed expansion gate"


def test_missing_adapter_summary_includes_all_expected_adapters(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["missing_adapter_summary"]["missing_adapters"] == list(MISSING_ADAPTERS)
    assert payload["missing_adapter_summary"]["planning_only"] is True
    assert payload["missing_adapter_summary"]["schedulers_implemented"] is False


def test_betrayal_feed_lab_only_true(tmp_path: Path) -> None:
    packet = _build(tmp_path / "logs", write=False)["betrayal_inverse_lab_feed_packet"]

    assert packet["lab_only"] is True


def test_betrayal_standard_55_policy_false(tmp_path: Path) -> None:
    packet = _build(tmp_path / "logs", write=False)["betrayal_inverse_lab_feed_packet"]

    assert packet["standard_55_policy_applies"] is False


def test_betrayal_source_chain_required(tmp_path: Path) -> None:
    packet = _build(tmp_path / "logs", write=False)["betrayal_inverse_lab_feed_packet"]

    assert packet["source_chain_required"] is True
    assert packet["original_vs_inverse_required"] is True
    assert packet["exact_risk_mapping_required"] is True
    assert packet["stale_shadow_outcomes_forbidden"] is True
    assert packet["preferred_win_rate_pct"] == 60
    assert packet["min_sample_count"] == 30
    assert packet["preferred_sample_count"] == 50
    assert packet["avg_pnl_requirement"] == "positive"


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE


def test_first_live_lane_change_allowed_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_live_lane_change_allowed"] is False


def test_recommended_r327_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["recommended_r327_path"]["phase"] == "R327 Human-Reviewed Observed Expansion Promotion Gate"
    assert payload["recommended_r327_path"]["can_alter_observed_expansion_after_human_review"] is True


def test_recommended_r328_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["recommended_r328_path"]["phase"] == "R328 Strategy Lab Evidence Adapter Implementation Pack"
    assert payload["recommended_r328_path"]["implements_r326_adapters"] is True


def test_no_promotion_event_write(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["promotion_event_written"] is False
    assert payload["feed_counts"]["promotion_event_written_count"] == 0


def test_no_risk_contract_write(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["risk_contract_config_mutated"] is False
    assert payload["feed_counts"]["risk_contract_write_required_count"] == 0


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
            "strategy-lab-candidate-feed-expansion",
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
    assert payload["candidate_feed_expansion_status"] == READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r326_strategy_lab_candidate_feed_expansion.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R326 CANDIDATE FEED EXPANSION FOR STRATEGY LAB VARIANTS" in result.stdout
    assert "candidate_feed_expansion_status" in result.stdout
    assert "FIRST TINY LIVE LANE" in result.stdout
    assert "FEED PACKET SUMMARY" in result.stdout
    assert "MISSING ADAPTER SUMMARY" in result.stdout
    assert "BETRAYAL/INVERSE LAB FEED" in result.stdout
    assert "RECOMMENDED R327/R328" in result.stdout
    assert "TINY LIVE PATH" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    return build_strategy_lab_candidate_feed_expansion(
        log_dir=log_dir,
        now=NOW,
        write=write,
        promotion_review_packet=_promotion_review_packet(),
        batch_runner_packet=_batch_runner_packet(),
    )


def _feed(payload: dict[str, object], feed_id: str) -> dict[str, object]:
    return next(row for row in payload["feed_expansion_packets"] if row["feed_id"] == feed_id)


def _promotion_review_packet() -> dict[str, object]:
    return {
        "promotion_review_status": "STRATEGY_LAB_PROMOTION_REVIEW_READY",
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
    }


def _batch_runner_packet() -> dict[str, object]:
    return {
        "batch_runner_status": "STRATEGY_LAB_VARIANT_BATCH_RUNNER_READY",
        "tiny_live_baseline_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
    }
