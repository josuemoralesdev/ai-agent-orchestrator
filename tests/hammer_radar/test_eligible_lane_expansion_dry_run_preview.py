from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview import (
    CURRENT_TINY_LIVE_LANE,
    DRY_RUN_PREVIEW_ELIGIBLE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PRIMARY_DRY_RUN_EXPANSION_LANES,
    build_eligible_lane_expansion_dry_run_preview,
    load_eligible_lane_expansion_dry_run_preview_records,
)

NOW = datetime(2026, 6, 24, 14, 0, tzinfo=UTC)
TIMER_PACKET = {"status": "TIMER_HEALTH_ACTIVE", "timer_active": True, "blockers": []}
FINAL_GATE_PACKET = {
    "status": "FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED",
    "blockers": ["final_submit_forbidden_in_r306_test"],
    "real_order_forbidden": True,
    "submit_allowed": False,
    "final_command_available": False,
    "current_real_candidate_lane_key": None,
    "requested_lane_key": CURRENT_TINY_LIVE_LANE,
}
FRESH_PACKET = {
    "status": "FRESH_TRIGGER_WAIT",
    "current_fresh_candidate_exists": False,
    "current_candidate_lane_key": None,
}


def test_module_runs_and_writes_preview_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir)
    records = load_eligible_lane_expansion_dry_run_preview_records(log_dir=log_dir, limit=10)

    assert payload["event_type"] == EVENT_TYPE
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1
    assert payload["expansion_gate_matrix"]["dry_run_expansion_candidates_count"] == 3


def test_current_first_tiny_live_lane_is_preserved_as_baseline(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir, write=False)
    by_lane = {row["lane_key"]: row for row in payload["lane_packets"]}

    assert payload["current_first_tiny_live_lane"] == CURRENT_TINY_LIVE_LANE
    assert payload["current_first_tiny_live_lane_unchanged"] is True
    assert payload["expansion_gate_matrix"]["current_first_lane_preserved"] is True
    assert by_lane[CURRENT_TINY_LIVE_LANE]["lane_role"] == "CURRENT_FIRST_TINY_LIVE_BASELINE"
    assert by_lane[CURRENT_TINY_LIVE_LANE]["expansion_preview_status"] == "BASELINE_UNCHANGED"


def test_primary_expansion_candidates_are_dry_run_preview_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir, write=False)
    by_lane = {row["lane_key"]: row for row in payload["lane_packets"]}

    assert payload["expansion_gate_matrix"]["primary_candidates"] == list(PRIMARY_DRY_RUN_EXPANSION_LANES)
    for lane in PRIMARY_DRY_RUN_EXPANSION_LANES:
        row = by_lane[lane]
        assert row["lane_role"] == "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE"
        assert row["expansion_preview_status"] == DRY_RUN_PREVIEW_ELIGIBLE
        assert row["submit_allowed"] is False
        assert row["final_command_available"] is False
        assert row["real_order_forbidden"] is True
        assert "future_human_decision_required_before_any_dry_run_scheduler_expansion" in row["expansion_blockers"]


def test_no_live_safety_flags_are_enabled(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir, write=False)

    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["global_kill_switch"] is True
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["secrets_shown"] is False
    assert payload["paper_live_separation_intact"] is True


def test_no_final_command_or_submit_allowed(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir, write=False)

    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["expansion_gate_matrix"]["submit_allowed"] is False
    assert payload["expansion_gate_matrix"]["final_command_available"] is False
    assert payload["final_gate_summary"]["submit_allowed"] is False
    assert payload["final_gate_summary"]["final_command_available"] is False


def test_no_arming_state_or_risk_contract_mutation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    root = Path(__file__).resolve().parents[2]
    arming_path = root / "configs/hammer_radar/autonomous_arming_state.json"
    risk_path = root / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_before = arming_path.read_text(encoding="utf-8")
    risk_before = risk_path.read_text(encoding="utf-8")

    payload = _build(log_dir, write=False)

    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["global_live_flags_changed"] is False


def test_betrayal_inverse_is_not_included_as_dry_run_expansion(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)

    payload = _build(log_dir, write=False)
    lane_keys = {row["lane_key"] for row in payload["lane_packets"]}
    rendered = json.dumps(payload)

    assert all("betrayal" not in lane.lower() for lane in lane_keys)
    assert payload["betrayal_policy"]["betrayal_inverse_included_as_dry_run_expansion"] is False
    assert "BETRAYAL_INVERSE_LANES" in payload["expansion_gate_matrix"]["rejected_candidates"]
    assert "BETRAYAL_LIVE_ALLOWED" not in rendered


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(log_dir)}

    result = subprocess.run(
        ["bash", "scripts/hammer_print_r306_eligible_lane_expansion_preview.sh"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R306 ELIGIBLE LANE EXPANSION DRY-RUN PREVIEW" in result.stdout
    assert "CURRENT FIRST TINY LIVE LANE" in result.stdout
    assert "FINAL LIVE SAFETY STATUS" in result.stdout
    assert "TIMER STATUS" in result.stdout
    assert "PAPER REFRESH HEALTH" in result.stdout
    assert "PRIMARY DRY-RUN EXPANSION CANDIDATES" in result.stdout
    assert "SECONDARY WATCH-ONLY CANDIDATES" in result.stdout
    assert "RISK-CONTRACT PREVIEW STATUS" in result.stdout
    assert "NO LIVE ENABLED / NO ARMING MUTATION" in result.stdout
    assert "RECOMMENDED R307 PATH" in result.stdout


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
            "eligible-lane-expansion-dry-run-preview",
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
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_no_secret_or_binance_order_surfaces_are_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = _build(log_dir, write=False)

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["safety"]["secrets_shown"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    return build_eligible_lane_expansion_dry_run_preview(
        log_dir=log_dir,
        now=NOW,
        write=write,
        timer_health_packet=TIMER_PACKET,
        final_gate_packet=FINAL_GATE_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
    )


def _seed_strategy_status(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "qualified_candidate_watch": {
            "live_qualified_lanes": [
                _lane("44m", "long", "ladder_close_50_618", 61.25, 80, 0.0529),
                _lane("44m", "short", "ladder_close_50_618", 60.47, 86, 0.098),
                _lane("55m", "long", "ladder_close_50_618", 62.96, 54, 0.1042),
            ],
            "near_miss_incubator_lanes": [],
            "paper_only_lanes": [],
        },
        "recommendations": [
            _lane("44m", "short", "ladder_382_50_618", 67.74, 62, 0.0963),
            _lane("44m", "short", "ladder_22_44_22", 66.04, 53, 0.068),
            _lane("44m", "long", "ladder_382_50_618", 62.9, 62, 0.0727),
            _lane("88m", "long", "ladder_382_50_618", 57.14, 42, 0.0613),
            _lane("55m", "long", "market_close", 60.0, 55, 0.0574),
        ],
    }
    with (log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _lane(timeframe: str, direction: str, entry_mode: str, win_rate_pct: float, sample_count: int, avg_pnl_pct: float) -> dict[str, object]:
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
