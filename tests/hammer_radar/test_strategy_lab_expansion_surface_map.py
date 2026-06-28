from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_expansion_surface_map import (
    BASELINE_LANE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PRIMARY_LANES,
    SECONDARY_WATCH_LANES,
    SAFETY,
    SURFACE_MAP_READY,
    TELEGRAM_SCOPE_COMPLETE_R322,
    build_strategy_lab_expansion_surface_map,
    load_strategy_lab_expansion_surface_map_records,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def test_builds_surface_map_ready_and_reports_telegram_scope(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    risk_path = _write_contracts(tmp_path)

    payload = _build(log_dir, risk_path)
    records = load_strategy_lab_expansion_surface_map_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["surface_map_status"] == SURFACE_MAP_READY
    assert payload["telegram_scope_status"] == TELEGRAM_SCOPE_COMPLETE_R322
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_baseline_primary_and_secondary_lanes_are_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    assert payload["baseline_lane"] == BASELINE_LANE
    assert [row["lane_key"] for row in payload["observed_primary_lanes"]] == list(PRIMARY_LANES)
    assert [row["lane_key"] for row in payload["observed_secondary_watch_lanes"]] == list(SECONDARY_WATCH_LANES)
    assert payload["current_tiny_live_status"]["submit_allowed"] is False
    assert payload["armed_tiny_live_lane"] == BASELINE_LANE


def test_risk_contract_config_is_read_not_written_and_reports_presence(tmp_path: Path) -> None:
    risk_path = _write_contracts(tmp_path)
    before = risk_path.read_text(encoding="utf-8")

    payload = _build(tmp_path / "logs", risk_path, write=False)

    assert risk_path.read_text(encoding="utf-8") == before
    summary = payload["risk_contract_summary"]
    assert summary["source_read_only"] is True
    assert summary["config_written"] is False
    assert summary["risk_contract_config_mutated"] is False
    assert summary["baseline_contract_present"] is True
    assert all(summary["observed_primary_contracts_present"].values())
    assert all(summary["observed_secondary_contracts_present"].values())
    assert summary["missing_contracts_for_observed_lanes"] == []
    assert summary["max_loss_usdt_by_lane"][BASELINE_LANE] == 4.44
    assert summary["leverage_by_lane"][BASELINE_LANE] == 10
    assert summary["notional_caps_by_lane"][BASELINE_LANE] == 80


def test_missing_contracts_are_reported_when_fixture_omits_lane(tmp_path: Path) -> None:
    omitted = PRIMARY_LANES[0]
    risk_path = _write_contracts(tmp_path, omit={omitted})

    payload = _build(tmp_path / "logs", risk_path, write=False)

    assert omitted in payload["risk_contract_summary"]["missing_contracts_for_observed_lanes"]
    assert payload["risk_contract_summary"]["observed_primary_contracts_present"][omitted] is False
    assert omitted in payload["missing_risk_contract_candidates"]


def test_promotion_near_miss_watch_blocked_and_lab_categories_are_reported(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    promotion = payload["promotion_candidate_summary"]
    assert BASELINE_LANE in promotion["promotion_ready_candidates"]
    assert PRIMARY_LANES[0] in promotion["promotion_ready_candidates"]
    assert "BTCUSDT|13m|long|ladder_close_50_618" in promotion["near_miss_candidates"]
    assert "BTCUSDT|8m|short|ladder_close_50_618" in promotion["paper_only_candidates"]
    assert SECONDARY_WATCH_LANES[-1] in promotion["watch_only_candidates"]
    assert "BETRAYAL_INVERSE_LANES" in promotion["lab_only_candidates"]
    assert "final_submit_forbidden" in payload["blocked_candidate_summary"]["common_blockers"]


def test_betrayal_inverse_is_lab_only_with_stricter_gate_fields(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    betrayal = payload["betrayal_inverse_summary"]
    assert betrayal["classification"] == "LAB_ONLY"
    assert betrayal["must_not_promote_to_tiny_live"] is True
    assert betrayal["betrayal_live_permission"] is False
    assert betrayal["standard_55_policy_applies"] is False
    assert betrayal["preferred_win_rate_pct"] == 60
    assert betrayal["minimum_sample_count"] == 30
    assert betrayal["preferred_sample_count"] == 50
    assert betrayal["avg_pnl_requirement"] == "positive"
    assert "original-vs-inverse comparison" in betrayal["required_checks"]
    assert "complete signal origin/source chain" in betrayal["required_checks"]
    assert "exact lane/entry/risk mapping" in betrayal["required_checks"]
    assert "no stale shadow outcomes" in betrayal["required_checks"]
    assert "beats normal candidates cleanly" in betrayal["required_checks"]


def test_recommended_r324_batch_plan_contains_required_groups(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)
    names = [row["name"] for row in payload["recommended_r324_batch_plan"]]

    assert "44m short variants" in names
    assert "55m long variants" in names
    assert "13m near-miss repair variants" in names
    assert "8m short capture-improvement variants" in names
    assert "88m watch-only evidence variants" in names
    assert "Betrayal/inverse lab-only variants" in names
    assert "MA/WMA200 anchor variants" in names
    assert "exit/TP/SL/trailing variants" in names


def test_strategy_dimensions_and_tiny_live_path_are_explicit(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    dimensions = payload["recommended_strategy_dimensions"]
    assert "ladder_close_50_618" in dimensions["entry_modes"]
    assert "ladder_382_50_618" in dimensions["entry_modes"]
    assert "ladder_22_44_22" in dimensions["entry_modes"]
    assert "market_close" in dimensions["entry_modes"]
    assert "WMA200 or MA200 anchor" in dimensions["filters"]
    assert "trailing" in dimensions["exits"]
    assert any("First Tiny Live remains baseline 44m long" in line for line in payload["recommended_tiny_live_path"])
    assert any("do not automatically become live" in line for line in payload["recommended_tiny_live_path"])


def test_required_safety_flags_block_live_mutations(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
    assert payload["no_live_mutation_summary"]["no_orders"] is True
    assert payload["no_live_mutation_summary"]["no_binance_order_or_test_order_endpoints"] is True
    assert payload["no_live_mutation_summary"]["no_config_or_env_mutation"] is True
    assert payload["no_live_mutation_summary"]["no_systemd_mutation"] is True
    assert payload["no_live_mutation_summary"]["no_telegram_send"] is True


def test_no_repo_config_env_arming_or_systemd_files_are_mutated(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    risk_path = root / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = root / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")
    env_before = dict(os.environ)

    payload = _build(tmp_path / "logs", _write_contracts(tmp_path), write=False)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert dict(os.environ) == env_before
    assert payload["config_written"] is False
    assert payload["env_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": "."}

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "strategy-lab-expansion-surface-map",
            "--no-write",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["surface_map_status"] == SURFACE_MAP_READY
    assert payload["submit_allowed"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r323_strategy_lab_expansion_surface_map.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(log_dir)},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    assert "R323 STRATEGY LAB EXPANSION RE-ENTRY AND CANDIDATE SURFACE MAP" in result.stdout
    assert "TELEGRAM SCOPE" in result.stdout
    assert "TINY LIVE STATUS" in result.stdout
    assert "OBSERVED PRIMARY LANES" in result.stdout
    assert "RISK CONTRACT SUMMARY" in result.stdout
    assert "PROMOTION CANDIDATE SUMMARY" in result.stdout
    assert "NEAR-MISS SUMMARY" in result.stdout
    assert "BETRAYAL / INVERSE LAB-ONLY SUMMARY" in result.stdout
    assert "RECOMMENDED R324 BATCH PLAN" in result.stdout
    assert "RECOMMENDED TINY LIVE PATH" in result.stdout
    assert "SAFETY FLAGS" in result.stdout


def _build(log_dir: Path, risk_path: Path, *, write: bool = True) -> dict[str, object]:
    log_dir.mkdir(parents=True, exist_ok=True)
    return build_strategy_lab_expansion_surface_map(
        log_dir=log_dir,
        now=NOW,
        write=write,
        risk_contract_path=risk_path,
        expansion_preview_packet=_expansion_packet(),
    )


def _expansion_packet() -> dict[str, object]:
    lanes = [
        _lane_packet(BASELINE_LANE, "BASELINE_UNCHANGED", "CURRENT_FIRST_TINY_LIVE_BASELINE", 82, 60.98, 0.0498),
        _lane_packet(PRIMARY_LANES[0], "DRY_RUN_PREVIEW_ELIGIBLE", "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE", 62, 67.74, 0.0963),
        _lane_packet(PRIMARY_LANES[1], "DRY_RUN_PREVIEW_ELIGIBLE", "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE", 86, 60.47, 0.098),
        _lane_packet(PRIMARY_LANES[2], "DRY_RUN_PREVIEW_ELIGIBLE", "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE", 54, 62.96, 0.1042),
        _lane_packet(SECONDARY_WATCH_LANES[0], "WATCH_ONLY", "SECONDARY_WATCH_ONLY_CANDIDATE", 53, 66.04, 0.068),
        _lane_packet(SECONDARY_WATCH_LANES[1], "WATCH_ONLY", "SECONDARY_WATCH_ONLY_CANDIDATE", 64, 62.5, 0.0647),
        _lane_packet(SECONDARY_WATCH_LANES[2], "WATCH_ONLY", "SECONDARY_WATCH_ONLY_CANDIDATE", 55, 60.0, 0.0574),
        _lane_packet(SECONDARY_WATCH_LANES[3], "WATCH_ONLY", "SECONDARY_WATCH_ONLY_CANDIDATE", 44, 56.82, 0.0667),
    ]
    return {
        "lane_packets": lanes,
        "final_gate_summary": {
            "status": "FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE",
            "blockers": [],
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "current_real_candidate_lane_key": None,
            "armed_lane_key": BASELINE_LANE,
        },
    }


def _lane_packet(
    lane_key: str,
    status: str,
    role: str,
    sample_count: int,
    win_rate_pct: float,
    avg_pnl_pct: float,
) -> dict[str, object]:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "lane_role": role,
        "expansion_preview_status": status,
        "direct_evidence_status": "DIRECT_PAPER_EVIDENCE",
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "exact_risk_contract_preview": {
            "exact_contract_found": True,
            "risk_contract_valid": True,
        },
        "expansion_blockers": [
            "live_execution_disabled_by_policy",
            "global_kill_switch_required",
            "final_submit_forbidden_in_r306",
        ],
    }


def _write_contracts(tmp_path: Path, *, omit: set[str] | None = None) -> Path:
    omit = omit or set()
    lanes = [BASELINE_LANE, *PRIMARY_LANES, *SECONDARY_WATCH_LANES]
    contracts = [_contract(lane) for lane in lanes if lane not in omit]
    path = tmp_path / "tiny_live_risk_contracts.json"
    path.write_text(json.dumps({"risk_contracts": contracts}, sort_keys=True), encoding="utf-8")
    return path


def _contract(lane_key: str) -> dict[str, object]:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "max_loss_usdt": 4.44,
        "leverage": 10,
        "margin_budget_usdt": 8,
        "max_position_notional_usdt": 80,
    }


def _seed_strategy_status(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "qualified_candidate_watch": {
            "live_qualified_lanes": [
                _strategy_lane("44m", "long", "ladder_close_50_618", 61.25, 80, 0.0529),
                _strategy_lane("44m", "short", "ladder_close_50_618", 60.47, 86, 0.098),
                _strategy_lane("55m", "long", "ladder_close_50_618", 62.96, 54, 0.1042),
            ],
            "near_miss_incubator_lanes": [
                _strategy_lane("13m", "long", "ladder_close_50_618", 54.0, 26, 0.01),
            ],
            "paper_only_lanes": [],
        },
        "recommendations": [
            _strategy_lane("44m", "short", "ladder_382_50_618", 67.74, 62, 0.0963),
            _strategy_lane("44m", "short", "ladder_22_44_22", 66.04, 53, 0.068),
            _strategy_lane("44m", "long", "ladder_382_50_618", 62.5, 64, 0.0647),
            _strategy_lane("55m", "long", "market_close", 60.0, 55, 0.0574),
            _strategy_lane("88m", "long", "ladder_382_50_618", 56.82, 44, 0.0667),
        ],
    }
    with (log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _strategy_lane(
    timeframe: str,
    direction: str,
    entry_mode: str,
    win_rate_pct: float,
    sample_count: int,
    avg_pnl_pct: float,
) -> dict[str, object]:
    return {
        "strategy_key": f"BTCUSDT|{timeframe}|{direction}|{entry_mode}",
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "sample_count": sample_count,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": avg_pnl_pct,
        "total_pnl_pct": round(avg_pnl_pct * sample_count, 4),
        "fill_rate_pct": 100.0,
        "stop_rate_pct": 20.0,
    }
