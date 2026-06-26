from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview import (
    build_eligible_lane_expansion_dry_run_preview,
)
from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
    build_expansion_risk_contract_preview_repair,
)
from src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler import (
    BASELINE_CURRENT_FIRST_TINY_LIVE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PRIMARY_DRY_RUN_OBSERVATION,
    SECONDARY_WATCH_ONLY_VISIBLE,
    SAFETY,
    build_multi_lane_dry_run_observation,
    load_multi_lane_dry_run_observation_records,
)

NOW = datetime(2026, 6, 26, 9, 0, tzinfo=UTC)
BASELINE = "BTCUSDT|44m|long|ladder_close_50_618"
PRIMARY = [
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
]
SECONDARY = [
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|88m|long|ladder_382_50_618",
]
TIMER_PACKET = {"status": "TIMER_HEALTH_ACTIVE", "timer_active": True, "blockers": []}
FRESH_PACKET = {
    "status": "FRESH_TRIGGER_WAIT",
    "current_fresh_candidate_exists": False,
    "current_candidate_lane_key": None,
}


def test_module_help_works() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.multi_lane_dry_run_observation_scheduler",
            "--help",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--preview" in result.stdout
    assert "--once" in result.stdout


def test_preview_default_does_not_write_config_or_ledger(tmp_path: Path) -> None:
    risk_path = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
    arming_path = Path("configs/hammer_radar/autonomous_arming_state.json")
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _build(tmp_path / "logs", write=False)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["preview_only"] is True
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False


def test_one_shot_observation_writes_only_observation_ledger(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    before = set(log_dir.glob("*")) if log_dir.exists() else set()

    payload = _build(log_dir, write=True)
    after = set(log_dir.glob("*"))
    records = load_multi_lane_dry_run_observation_records(log_dir=log_dir, limit=10)

    assert payload["preview_only"] is False
    assert (log_dir / LEDGER_FILENAME).exists()
    assert after - before == {log_dir / LEDGER_FILENAME}
    assert len(records) == 1
    assert records[0]["event_type"] == EVENT_TYPE


def test_baseline_primary_and_secondary_lanes_are_classified(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs")
    by_lane = {row["lane_key"]: row for row in payload["lane_packets"]}

    assert by_lane[BASELINE]["lane_role"] == BASELINE_CURRENT_FIRST_TINY_LIVE
    assert payload["multi_lane_observation_gate_matrix"]["baseline_lane_preserved"] is True
    for lane in PRIMARY:
        assert by_lane[lane]["lane_role"] == PRIMARY_DRY_RUN_OBSERVATION
    for lane in SECONDARY:
        assert by_lane[lane]["lane_role"] == SECONDARY_WATCH_ONLY_VISIBLE
        assert by_lane[lane]["observation_action"] == "WATCH_ONLY_NO_SUBMIT"
        assert by_lane[lane]["observation_status"] == "WATCH_ONLY_VISIBLE"


def test_betrayal_inverse_is_not_included_as_observed_lane(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs")
    lane_keys = [row["lane_key"] for row in payload["lane_packets"]]
    rendered = json.dumps(payload).lower()

    assert all("betrayal" not in lane.lower() for lane in lane_keys)
    assert payload["betrayal_policy"]["betrayal_inverse_included_as_observed_lane"] is False
    assert "betrayal_live_allowed" not in rendered


def test_all_safety_flags_remain_locked_and_no_payloads(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs")

    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
    for row in payload["lane_packets"]:
        for key, expected in SAFETY.items():
            assert row[key] is expected
        assert row["dry_run_order_payload_created"] is False
        assert row["executable_payload_created"] is False
        assert row["signed_request_created"] is False
        assert row["submit_allowed"] is False
        assert row["final_command_available"] is False


def test_no_binance_or_secret_surfaces_are_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _build(tmp_path / "logs")

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False
    assert payload["secrets_shown"] is False


def test_no_arming_or_risk_contract_mutation(tmp_path: Path) -> None:
    risk_path = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
    arming_path = Path("configs/hammer_radar/autonomous_arming_state.json")
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _build(tmp_path / "logs", write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["config_written"] is False
    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "multi-lane-dry-run-observation",
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
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r310_multi_lane_dry_run_observation.sh"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R310 MULTI-LANE DRY-RUN OBSERVATION SCHEDULER" in result.stdout
    assert "BASELINE LANE" in result.stdout
    assert "PRIMARY OBSERVED LANES" in result.stdout
    assert "SECONDARY WATCH-ONLY LANES" in result.stdout
    assert "RISK-CONTRACT READINESS" in result.stdout
    assert "TIMER HEALTH" in result.stdout
    assert "CANDIDATE VISIBILITY SUMMARY" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "recommended_r311_path" in result.stdout


def test_r306_r307_compatibility_after_r309_contracts_remains_intact(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    r306 = build_eligible_lane_expansion_dry_run_preview(
        log_dir=log_dir,
        write=False,
        now=NOW,
        timer_health_packet=TIMER_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
        final_gate_packet={
            "status": "FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED",
            "blockers": [],
            "real_order_forbidden": True,
            "submit_allowed": False,
            "final_command_available": False,
            "requested_lane_key": BASELINE,
        },
    )
    r307 = build_expansion_risk_contract_preview_repair(log_dir=log_dir, write=False, now=NOW)
    r310 = _build(log_dir)

    for payload in (r306, r307, r310):
        by_lane = {row["lane_key"]: row for row in payload["lane_packets"]}
        for lane in [BASELINE, *PRIMARY]:
            row = by_lane[lane]
            risk = row.get("exact_risk_contract_preview", row)
            assert risk["exact_contract_found"] is True
            assert risk["risk_contract_valid"] is True


def _build(log_dir: Path, *, write: bool = False) -> dict[str, object]:
    return build_multi_lane_dry_run_observation(
        log_dir=log_dir,
        write=write,
        now=NOW,
        timer_health_packet=TIMER_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
    )
