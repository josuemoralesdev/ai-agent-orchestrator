from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_promotion_review_packet import (
    BASELINE_LANE,
    EVENT_TYPE,
    LAB_ONLY_LANES,
    LEDGER_FILENAME,
    NEEDS_MORE_SAMPLES_LANES,
    READY,
    REVIEW_READY_LANES,
    SAFETY,
    WATCH_ONLY_LANES,
    build_strategy_lab_promotion_review_packet,
    load_strategy_lab_promotion_review_packet_records,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def test_builds_ready_promotion_review_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = _build(log_dir)
    records = load_strategy_lab_promotion_review_packet_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["promotion_review_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_review_ready_candidates_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["lane_key"] for row in payload["review_ready_candidates"]] == list(REVIEW_READY_LANES)
    assert all(row["source_bucket"] == "ready_for_R325_review" for row in payload["review_ready_candidates"])


def test_needs_more_samples_candidates_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["lane_key"] for row in payload["needs_more_samples_candidates"]] == list(NEEDS_MORE_SAMPLES_LANES)
    assert all(row["recommended_decision"] == "NEEDS_MORE_EVIDENCE" for row in payload["needs_more_samples_candidates"])


def test_watch_only_candidates_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert [row["lane_key"] for row in payload["watch_only_candidates"]] == list(WATCH_ONLY_LANES)
    assert payload["watch_only_candidates"][0]["source_bucket"] == "watch_only"


def test_betrayal_inverse_lab_only_included(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["lab_only_candidates"] == list(LAB_ONLY_LANES)
    assert payload["betrayal_inverse_review_packet"]["lab_only"] is True
    assert payload["betrayal_inverse_review_packet"]["tiny_live_eligible_now"] is False


def test_betrayal_standard_55_policy_false(tmp_path: Path) -> None:
    betrayal = _build(tmp_path / "logs", write=False)["betrayal_inverse_review_packet"]

    assert betrayal["standard_55_policy_applies"] is False


def test_betrayal_stricter_gate_fields_present(tmp_path: Path) -> None:
    betrayal = _build(tmp_path / "logs", write=False)["betrayal_inverse_review_packet"]

    assert betrayal["preferred_win_rate_pct"] == 60
    assert betrayal["min_sample_count"] == 30
    assert betrayal["preferred_sample_count"] == 50
    assert betrayal["avg_pnl_requirement"] == "positive"
    assert betrayal["original_vs_inverse_required"] is True
    assert betrayal["source_chain_required"] is True
    assert betrayal["exact_risk_mapping_required"] is True
    assert betrayal["stale_shadow_outcomes_forbidden"] is True
    assert betrayal["promotion_review_allowed"] is False
    assert betrayal["live_permission"] is False


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE


def test_first_live_lane_change_allowed_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_live_lane_change_allowed"] is False


def test_review_ready_candidates_have_live_permission_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert all(row["live_permission"] is False for row in payload["review_ready_candidates"])


def test_review_ready_candidates_have_tiny_live_eligible_now_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert all(row["tiny_live_eligible_now"] is False for row in payload["review_ready_candidates"])


def test_human_review_required_true(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["human_review_required"] is True
    assert all(row["human_review_required"] is True for row in payload["review_ready_candidates"])


def test_promotion_event_written_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["promotion_event_written"] is False
    assert payload["promotion_policy_summary"]["writes_promotion_events"] is False


def test_risk_contract_config_mutated_false(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["risk_contract_config_mutated"] is False
    assert payload["risk_contract_review_summary"]["risk_contract_config_mutated"] is False


def test_risk_contracts_read_but_not_written(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    risk_path = root / "configs/hammer_radar/tiny_live_risk_contracts.json"
    before = risk_path.read_text(encoding="utf-8")

    payload = _build(tmp_path / "logs", write=False)

    assert risk_path.read_text(encoding="utf-8") == before
    assert payload["risk_contract_review_summary"]["source_read_only"] is True
    assert payload["risk_contract_review_summary"]["config_written"] is False


def test_review_ready_contracts_present_valid_summarized(tmp_path: Path) -> None:
    risk = _build(tmp_path / "logs", write=False)["risk_contract_review_summary"]

    assert set(REVIEW_READY_LANES).issubset(set(risk["contracts_present_for_review_ready"]))
    assert risk["contracts_missing_for_review_ready"] == []
    assert risk["all_review_ready_contracts_valid"] is True


def test_r326_recommendation_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["recommended_r326_path"]["phase"] == "R326 Candidate Feed Expansion for Strategy Lab Variants"


def test_r327_recommendation_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["recommended_r327_path"]["phase"] == "R327 Human-Reviewed Observed Expansion Promotion Gate"


def test_tiny_live_path_says_wait_for_real_candidate(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert any("wait for real candidate detection" in line for line in payload["recommended_tiny_live_path"])


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
            "strategy-lab-promotion-review-packet",
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
    assert payload["promotion_review_status"] == READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r325_strategy_lab_promotion_review_packet.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R325 STRATEGY LAB PROMOTION REVIEW PACKET" in result.stdout
    assert "FIRST TINY LIVE LANE" in result.stdout
    assert "REVIEW-READY CANDIDATES" in result.stdout
    assert "OBSERVED EXPANSION REVIEW CANDIDATES" in result.stdout
    assert "FUTURE TINY-LIVE REVIEW CANDIDATES" in result.stdout
    assert "NEEDS-MORE-SAMPLES CANDIDATES" in result.stdout
    assert "WATCH-ONLY CANDIDATES" in result.stdout
    assert "BETRAYAL/INVERSE LAB-ONLY PACKET" in result.stdout
    assert "RISK CONTRACT SUMMARY" in result.stdout
    assert "RECOMMENDED OPERATOR DECISIONS" in result.stdout
    assert "RECOMMENDED R326/R327 PATH" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def test_required_safety_fields_are_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    return build_strategy_lab_promotion_review_packet(
        log_dir=log_dir,
        now=NOW,
        write=write,
        batch_runner_packet=_batch_runner_packet(),
        surface_map_packet=_surface_map_packet(),
    )


def _batch_runner_packet() -> dict[str, object]:
    return {
        "batch_runner_status": "STRATEGY_LAB_VARIANT_BATCH_RUNNER_READY",
        "batch_results": [
            {
                "batch_id": "44m_short",
                "current_evidence_snapshot": {
                    "BTCUSDT|44m|short|ladder_382_50_618": _evidence(68, 69.12, 0.1186),
                    "BTCUSDT|44m|short|ladder_close_50_618": _evidence(94, 61.7, 0.1081),
                    "BTCUSDT|44m|short|ladder_22_44_22": _evidence(57, 68.42, 0.0836),
                },
            },
            {
                "batch_id": "55m_long",
                "current_evidence_snapshot": {
                    "BTCUSDT|55m|long|ladder_close_50_618": _evidence(58, 58.62, 0.089),
                    "BTCUSDT|55m|long|market_close": _evidence(59, 55.93, 0.0402),
                },
            },
            {
                "batch_id": "13m_near_miss",
                "current_evidence_snapshot": {
                    "BTCUSDT|13m|long|ladder_close_50_618": _evidence(324, 45.68, 0.0067),
                    "BTCUSDT|13m|short|ladder_close_50_618": _evidence(317, 49.53, 0.0256),
                },
            },
            {
                "batch_id": "8m_short_capture",
                "current_evidence_snapshot": {
                    "BTCUSDT|8m|short|ladder_close_50_618": _evidence(564, 54.61, 0.022),
                },
            },
            {
                "batch_id": "88m_watch",
                "current_evidence_snapshot": {
                    "BTCUSDT|88m|long|ladder_382_50_618": _evidence(45, 57.78, 0.07),
                },
            },
        ],
    }


def _surface_map_packet() -> dict[str, object]:
    return {
        "surface_map_status": "STRATEGY_LAB_SURFACE_MAP_READY",
        "telegram_scope_status": "TELEGRAM_SCOPE_COMPLETE_R322",
        "current_tiny_live_status": {
            "status": "FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE",
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "tiny_live_waiting_for_real_candidate": True,
        },
        "observed_primary_lanes": [
            {"lane_key": "BTCUSDT|44m|short|ladder_382_50_618"},
            {"lane_key": "BTCUSDT|44m|short|ladder_close_50_618"},
            {"lane_key": "BTCUSDT|55m|long|ladder_close_50_618"},
        ],
        "observed_secondary_watch_lanes": [
            {"lane_key": "BTCUSDT|44m|short|ladder_22_44_22"},
            {"lane_key": "BTCUSDT|44m|long|ladder_382_50_618"},
            {"lane_key": "BTCUSDT|55m|long|market_close"},
            {"lane_key": "BTCUSDT|88m|long|ladder_382_50_618"},
        ],
    }


def _evidence(sample_count: int, win_rate_pct: float, avg_pnl_pct: float) -> dict[str, object]:
    return {
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "evidence_status": "DIRECT_PAPER_EVIDENCE",
        "source_chain": ["test_source"],
    }
