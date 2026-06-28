from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_variant_batch_runner import (
    BASELINE_LANE,
    BATCH_IDS,
    EVENT_TYPE,
    LEDGER_FILENAME,
    READY,
    SAFETY,
    build_strategy_lab_variant_batch_runner,
    load_strategy_lab_variant_batch_runner_records,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def test_builds_ready_batch_runner_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_variant_batch_runner_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["batch_runner_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_includes_all_8_required_batch_groups(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["batch_id"] for row in payload["batch_results"]] == list(BATCH_IDS)
    assert payload["batch_counts"]["batch_count"] == 8


def test_44m_short_batch_includes_three_candidate_lanes(tmp_path: Path) -> None:
    batch = _batch(_build(tmp_path / "logs", write=False), "44m_short")

    assert batch["candidate_lanes"] == [
        "BTCUSDT|44m|short|ladder_382_50_618",
        "BTCUSDT|44m|short|ladder_close_50_618",
        "BTCUSDT|44m|short|ladder_22_44_22",
    ]
    assert "entry modes" in batch["variants_to_test"]
    assert "WMA/MA anchor" in batch["variants_to_test"]


def test_55m_long_batch_includes_ladder_and_market_close(tmp_path: Path) -> None:
    batch = _batch(_build(tmp_path / "logs", write=False), "55m_long")

    assert batch["candidate_lanes"] == ["BTCUSDT|55m|long|ladder_close_50_618", "BTCUSDT|55m|long|market_close"]
    assert "ladder vs market close" in batch["variants_to_test"]


def test_near_miss_and_capture_watch_batches_are_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert _batch(payload, "13m_near_miss")["candidate_lanes"] == [
        "BTCUSDT|13m|long|ladder_close_50_618",
        "BTCUSDT|13m|short|ladder_close_50_618",
    ]
    assert _batch(payload, "8m_short_capture")["candidate_lanes"] == ["BTCUSDT|8m|short|ladder_close_50_618"]
    assert _batch(payload, "88m_watch")["candidate_lanes"] == ["BTCUSDT|88m|long|ladder_382_50_618"]


def test_betrayal_inverse_batch_marked_lab_only_with_stricter_gates(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    betrayal = _batch(payload, "betrayal_inverse_lab")

    assert betrayal["lab_only"] is True
    assert betrayal["tiny_live_eligible_now"] is False
    assert betrayal["standard_55_policy_applies"] is False
    assert betrayal["preferred_win_rate_pct"] == 60
    assert betrayal["min_sample_count"] == 30
    assert betrayal["preferred_sample_count"] == 50
    assert betrayal["avg_pnl_requirement"] == "positive"
    assert betrayal["original_vs_inverse_required"] is True
    assert betrayal["source_chain_required"] is True
    assert betrayal["exact_risk_mapping_required"] is True
    assert betrayal["stale_shadow_outcomes_forbidden"] is True
    assert payload["betrayal_inverse_lab_packet"]["lab_only"] is True


def test_ma_wma_anchor_and_exit_batches_are_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    ma = _batch(payload, "ma_wma_anchor")
    exits = _batch(payload, "exits")
    assert "WMA200 support/resistance anchor" in ma["variants_to_test"]
    assert "MA200 support/resistance anchor" in ma["variants_to_test"]
    assert "golden-pocket + anchor confluence" in ma["variants_to_test"]
    assert "fixed TP/SL" in exits["variants_to_test"]
    assert "trailing" in exits["variants_to_test"]
    assert "invalidation tightening" in exits["variants_to_test"]


def test_promotion_candidates_are_separated_from_lab_only(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    promo = payload["promotion_review_candidates"]

    assert "BTCUSDT|44m|short|ladder_382_50_618" in promo["ready_for_R325_review"]
    assert "BTCUSDT|13m|long|ladder_close_50_618" in promo["needs_more_samples"]
    assert "BTCUSDT|88m|long|ladder_382_50_618" in promo["watch_only"]
    assert "BETRAYAL_INVERSE_LANES" in promo["lab_only"]
    assert "BETRAYAL_INVERSE_LANES" not in promo["ready_for_R325_review"]
    assert "BTCUSDT|13m|long|ladder_close_50_618" not in promo["ready_for_R325_review"]
    assert "BTCUSDT|88m|long|ladder_382_50_618" not in promo["ready_for_R325_review"]


def test_tiny_live_baseline_lane_preserved_and_first_lane_change_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["tiny_live_baseline_lane"] == BASELINE_LANE
    assert payload["first_live_lane_change_allowed"] is False
    assert any("First Tiny Live remains BTCUSDT|44m|long|ladder_close_50_618" in line for line in payload["recommended_tiny_live_path"])


def test_no_promotion_risk_contract_config_env_arming_systemd_live_submit_final_or_telegram_mutations(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    risk_path = root / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = root / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")
    env_before = dict(os.environ)

    payload = _build(tmp_path / "logs", write=False)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert dict(os.environ) == env_before
    assert payload["recommended_r325_promotion_review"]["write_promotion_events"] is False
    assert payload["recommended_r325_promotion_review"]["write_risk_contracts"] is False
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
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
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "strategy-lab-variant-batch-runner",
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
    assert payload["batch_runner_status"] == READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r324_strategy_lab_variant_batch_runner.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R324 STRATEGY LAB VARIANT BATCH RUNNER" in result.stdout
    assert "TELEGRAM SCOPE STATUS" in result.stdout
    assert "TINY LIVE BASELINE LANE" in result.stdout
    assert "BATCH RESULTS SUMMARY" in result.stdout
    assert "PROMOTION REVIEW CANDIDATES" in result.stdout
    assert "NEAR-MISS REPAIR CANDIDATES" in result.stdout
    assert "BETRAYAL/INVERSE LAB-ONLY PACKET" in result.stdout
    assert "MA/WMA ANCHOR PACKET" in result.stdout
    assert "EXIT VARIANT PACKET" in result.stdout
    assert "RECOMMENDED R325 AND R326" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    return build_strategy_lab_variant_batch_runner(
        log_dir=log_dir,
        now=NOW,
        write=write,
        surface_map_packet=_surface_packet(),
        variant_pack_packet=_variant_pack(),
    )


def _batch(payload: dict[str, object], batch_id: str) -> dict[str, object]:
    return next(row for row in payload["batch_results"] if row["batch_id"] == batch_id)


def _surface_packet() -> dict[str, object]:
    return {
        "surface_map_status": "STRATEGY_LAB_SURFACE_MAP_READY",
        "telegram_scope_status": "TELEGRAM_SCOPE_COMPLETE_R322",
        "observed_primary_lanes": [
            _lane("BTCUSDT|44m|short|ladder_382_50_618", 62, 67.74, 0.0963),
            _lane("BTCUSDT|44m|short|ladder_close_50_618", 86, 60.47, 0.098),
            _lane("BTCUSDT|55m|long|ladder_close_50_618", 54, 62.96, 0.1042),
        ],
        "observed_secondary_watch_lanes": [
            _lane("BTCUSDT|44m|short|ladder_22_44_22", 53, 66.04, 0.068),
            _lane("BTCUSDT|44m|long|ladder_382_50_618", 64, 62.5, 0.0647),
            _lane("BTCUSDT|55m|long|market_close", 55, 60.0, 0.0574),
            _lane("BTCUSDT|88m|long|ladder_382_50_618", 44, 56.82, 0.0667),
        ],
    }


def _variant_pack() -> dict[str, object]:
    return {
        "variant_candidates": [
            _variant("BTCUSDT|13m|long|ladder_close_50_618", 24, 54.0, 0.021),
            _variant("BTCUSDT|13m|short|ladder_close_50_618", 22, 53.0, 0.018),
            _variant("BTCUSDT|8m|short|ladder_close_50_618", 28, 54.5, 0.019),
        ],
        "top_variant_candidates": [
            _variant("BTCUSDT|44m|short|ladder_382_50_618", 62, 67.74, 0.0963),
            _variant("BTCUSDT|44m|short|ladder_close_50_618", 86, 60.47, 0.098),
            _variant("BTCUSDT|55m|long|ladder_close_50_618", 54, 62.96, 0.1042),
            _variant("BTCUSDT|55m|long|market_close", 55, 60.0, 0.0574),
        ],
        "top_near_miss_variant_opportunities": [
            _variant("BTCUSDT|13m|long|ladder_close_50_618", 24, 54.0, 0.021),
            _variant("BTCUSDT|8m|short|ladder_close_50_618", 28, 54.5, 0.019),
        ],
    }


def _lane(lane_key: str, sample_count: int, win_rate_pct: float, avg_pnl_pct: float) -> dict[str, object]:
    return {
        "lane_key": lane_key,
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "expansion_preview_status": "DRY_RUN_PREVIEW_ELIGIBLE",
        "source_chain": ["fixture"],
    }


def _variant(lane_key: str, sample_count: int, win_rate_pct: float, avg_pnl_pct: float) -> dict[str, object]:
    return {
        "lane_key": lane_key,
        "direct_sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "evidence_status": "DIRECT_PAPER_EVIDENCE",
        "recommended_lab_action": "EXPANSION_PREVIEW_ONLY",
        "source_chain": ["fixture"],
    }
