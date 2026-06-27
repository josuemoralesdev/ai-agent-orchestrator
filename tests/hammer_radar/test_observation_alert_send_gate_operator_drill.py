from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import CONFIRMATION_PHRASE
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    WARNING_PREVIEW_NO_SEND,
)
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    DRILL_PASSED,
    EVENT_TYPE,
    LEDGER_FILENAME,
    SCENARIO_FINAL_SAFETY_VIOLATION,
    SCENARIO_HEALTHY,
    SCENARIO_STALE_OBSERVATION,
    build_observation_alert_send_gate_operator_drill,
    build_synthetic_health_panel,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_healthy_scenario_passes_no_send(tmp_path: Path) -> None:
    payload = _drill(tmp_path, SCENARIO_HEALTHY)
    result = payload["scenario_results"][0]

    assert payload["event_type"] == EVENT_TYPE
    assert result["passed"] is True
    assert result["observed_alert_required"] is False
    assert result["observed_send_gate_status"] == "SEND_GATE_BLOCKED_NO_ALERT_REQUIRED"
    assert result["telegram_send_called"] is False
    assert result["real_telegram_send_called"] is False


def test_stale_observation_scenario_creates_alert_required_synthetic_payload(tmp_path: Path) -> None:
    payload = _drill(tmp_path, SCENARIO_STALE_OBSERVATION)
    result = payload["scenario_results"][0]

    assert result["synthetic_scenario"] is True
    assert result["synthetic_inputs_used"] is True
    assert result["observed_alert_required"] is True
    assert result["observed_alert_severity"] in {WARNING_PREVIEW_NO_SEND, CRITICAL_PREVIEW_NO_SEND}
    assert "stale_observation_tick" in result["observed_alert_reasons"]


def test_stale_observation_missing_confirmation_blocks_send(tmp_path: Path) -> None:
    result = _result(_drill(tmp_path, SCENARIO_STALE_OBSERVATION), SCENARIO_STALE_OBSERVATION)
    missing = _attempt(result, "missing_confirmation_blocks")

    assert missing["send_gate_status"] == "SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED"
    assert missing["telegram_send_called"] is False
    assert missing["telegram_message_sent"] is False


def test_stale_observation_exact_confirmation_mock_sends_only(tmp_path: Path) -> None:
    result = _result(_drill(tmp_path, SCENARIO_STALE_OBSERVATION), SCENARIO_STALE_OBSERVATION)
    exact = _attempt(result, "exact_confirmation_mock_send")

    assert exact["send_gate_status"] == "SEND_GATE_MOCK_SENT"
    assert exact["confirmation_phrase_matched"] is True
    assert exact["telegram_send_called"] is True
    assert exact["telegram_message_sent"] is True
    assert exact["real_telegram_send_called"] is False
    assert exact["real_telegram_message_sent"] is False


def test_final_safety_violation_scenario_creates_critical_alert(tmp_path: Path) -> None:
    result = _result(_drill(tmp_path, SCENARIO_FINAL_SAFETY_VIOLATION), SCENARIO_FINAL_SAFETY_VIOLATION)

    assert result["observed_alert_required"] is True
    assert result["observed_alert_severity"] == CRITICAL_PREVIEW_NO_SEND
    assert "final_live_safety_submit_allowed" in result["observed_alert_reasons"]
    assert "final_live_safety_final_command_available" in result["observed_alert_reasons"]


def test_final_safety_violation_exact_confirmation_mock_sends_only(tmp_path: Path) -> None:
    result = _result(_drill(tmp_path, SCENARIO_FINAL_SAFETY_VIOLATION), SCENARIO_FINAL_SAFETY_VIOLATION)
    exact = _attempt(result, "exact_confirmation_mock_send")

    assert exact["send_gate_status"] == "SEND_GATE_MOCK_SENT"
    assert exact["telegram_send_called"] is True
    assert exact["real_telegram_send_called"] is False
    assert result["source_alert_preview"]["source_health_panel"]["final_live_safety"]["submit_allowed"] is True
    assert result["submit_allowed"] is False if "submit_allowed" in result else True


def test_wrong_confirmation_blocks(tmp_path: Path) -> None:
    result = _result(
        _drill(tmp_path, SCENARIO_STALE_OBSERVATION, confirmation="WRONG CONFIRMATION"),
        SCENARIO_STALE_OBSERVATION,
    )
    wrong = _attempt(result, "wrong_confirmation_blocks")
    operator_wrong = _attempt(result, "operator_supplied_confirmation_blocks")

    assert wrong["send_gate_status"] == "SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED"
    assert operator_wrong["send_gate_status"] == "SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED"
    assert result["operator_confirmation_matched"] is False


def test_real_telegram_flags_remain_false_in_all_scenarios(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _drill(tmp_path, "all")

    urlopen.assert_not_called()
    assert payload["no_real_telegram_passed"] is True
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    for result in payload["scenario_results"]:
        assert result["real_telegram_send_called"] is False
        assert result["real_telegram_message_sent"] is False
        assert result["no_real_telegram_passed"] is True


def test_drill_all_scenarios_returns_operator_drill_passed(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all", write=True)

    assert payload["drill_status"] == DRILL_PASSED
    assert payload["healthy_no_send_passed"] is True
    assert payload["stale_alert_mock_send_gate_passed"] is True
    assert payload["final_safety_critical_mock_send_gate_passed"] is True
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_drill_output_marks_synthetic_and_real_runtime_not_mutated(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["synthetic_scenario"] is True
    assert payload["synthetic_inputs_used"] is True
    assert payload["real_runtime_mutated"] is False
    for result in payload["scenario_results"]:
        assert result["synthetic_scenario"] is True
        assert result["real_runtime_mutated"] is False


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _drill(tmp_path, "all")

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["systemd_unit_mutated"] is False
    assert payload["scheduler_started"] is False


def test_no_live_order(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = _drill(tmp_path, "all")

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _drill(tmp_path, "all")

    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["leverage_change_called"] is False
    assert payload["margin_change_called"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "observation-alert-send-gate-operator-drill",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["drill_status"] == DRILL_PASSED
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r317_observation_alert_send_gate_operator_drill.sh"
    text = script.read_text(encoding="utf-8")

    assert "telegram-sender-mode real" not in text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    for section in (
        "DRILL STATUS",
        "SCENARIOS RUN",
        "HEALTHY NO-SEND RESULT",
        "STALE OBSERVATION RESULT",
        "FINAL SAFETY VIOLATION RESULT",
        "CONFIRMATION GATE RESULT",
        "MOCK/REAL SEND FLAGS",
        "SAFETY FLAGS",
        "RECOMMENDED NEXT PHASE",
    ):
        assert section in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert "sendMessage" not in result.stdout


def test_r316_r315_r314_compatibility_remains_intact(tmp_path: Path) -> None:
    health = build_synthetic_health_panel(
        scenario_name=SCENARIO_STALE_OBSERVATION,
        now=NOW,
        max_age_seconds=180,
    )
    payload = _drill(tmp_path, SCENARIO_STALE_OBSERVATION)
    result = payload["scenario_results"][0]

    assert health["event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert result["source_alert_preview"]["event_type"] == "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
    assert result["gate_attempts"][-1]["send_gate_status"] == "SEND_GATE_MOCK_SENT"


def _drill(
    tmp_path: Path,
    scenario: str,
    *,
    confirmation: str | None = CONFIRMATION_PHRASE,
    write: bool = False,
) -> dict[str, object]:
    return build_observation_alert_send_gate_operator_drill(
        log_dir=tmp_path,
        scenario=scenario,
        confirmation=confirmation,
        now=NOW,
        write=write,
    )


def _result(payload: dict[str, object], scenario_name: str) -> dict[str, object]:
    for result in payload["scenario_results"]:
        if result["scenario_name"] == scenario_name:
            return result
    raise AssertionError(f"missing scenario result {scenario_name}")


def _attempt(result: dict[str, object], attempt_name: str) -> dict[str, object]:
    for attempt in result["gate_attempts"]:
        if attempt["attempt_name"] == attempt_name:
            return attempt
    raise AssertionError(f"missing gate attempt {attempt_name}")
