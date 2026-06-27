from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.multi_lane_observation_alert_send_gate import (
    build_multi_lane_observation_alert_send_gate,
)
from src.app.hammer_radar.operator.multi_lane_observation_alerting_preview import (
    CRITICAL_PREVIEW_NO_SEND,
    WARNING_PREVIEW_NO_SEND,
)
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    build_synthetic_health_panel,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    FUTURE_CONFIRMATION_PHRASE,
    build_real_telegram_observation_alert_send_preview,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview import (
    DRILL_FAILED,
    DRILL_PASSED,
    EVENT_TYPE,
    LEDGER_FILENAME,
    SCENARIO_HEALTHY,
    SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    build_real_telegram_observation_alert_synthetic_send_drill_preview,
    format_synthetic_send_drill_json,
    format_synthetic_send_drill_text,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_TOKEN = "1234:abcdefghijklmnopqrstuvwxyz"
RAW_CHAT_ID = "-1001234567890"


def test_credentials_ready_from_injected_env(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

    assert payload["event_type"] == EVENT_TYPE
    assert payload["drill_status"] == DRILL_PASSED
    assert payload["credentials_ready"] is True
    assert payload["telegram_config_readiness"]["telegram_config_source_kind"] == "env"
    assert payload["real_send_available_for_future"] is True


def test_credentials_ready_from_injected_private_env_file_fallback(tmp_path: Path) -> None:
    env_file = _write_env_file(tmp_path)
    payload = _drill(tmp_path, env={}, env_file_path=env_file)

    assert payload["credentials_ready"] is True
    assert payload["telegram_config_readiness"]["telegram_config_source_kind"] == "private_env_file"
    assert payload["telegram_config_readiness"]["telegram_config_source_path"] == str(env_file)
    assert payload["real_send_available_for_future"] is True


def test_missing_credentials_fail_drill_and_block_future_real_send(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env={}, env_file_path=tmp_path / "missing.env")

    assert payload["drill_status"] == DRILL_FAILED
    assert payload["credentials_ready"] is False
    assert payload["real_send_available_for_future"] is False
    assert "real_credentials_not_ready" in payload["drill_blockers"]


def test_healthy_scenario_blocks_send_by_no_heartbeat_policy(tmp_path: Path) -> None:
    result = _result(_drill(tmp_path, scenario=SCENARIO_HEALTHY, env=_env()), SCENARIO_HEALTHY)

    assert result["pass"] is True
    assert result["observed_alert_required"] is False
    assert result["observed_alert_severity"] == "INFO_PREVIEW_NO_SEND"
    assert result["future_real_send_eligible_after_exact_phrase"] is False
    assert result["source_real_telegram_preview"]["healthy_state_send_blocked"] is True


def test_synthetic_stale_observation_produces_actionable_alert(tmp_path: Path) -> None:
    result = _result(
        _drill(tmp_path, scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION, env=_env()),
        SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    )

    assert result["pass"] is True
    assert result["synthetic_scenario"] is True
    assert result["synthetic_inputs_used"] is True
    assert result["observed_alert_required"] is True
    assert result["observed_alert_severity"] in {WARNING_PREVIEW_NO_SEND, CRITICAL_PREVIEW_NO_SEND}
    assert "stale_observation_tick" in result["observed_alert_reasons"]
    assert result["future_real_send_eligible_after_exact_phrase"] is True


def test_synthetic_final_safety_violation_produces_critical_preview_no_send(tmp_path: Path) -> None:
    result = _result(
        _drill(tmp_path, scenario=SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION, env=_env()),
        SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
    )

    assert result["observed_alert_required"] is True
    assert result["observed_alert_severity"] == CRITICAL_PREVIEW_NO_SEND
    assert "final_live_safety_submit_allowed" in result["observed_alert_reasons"]
    assert "final_live_safety_final_command_available" in result["observed_alert_reasons"]
    assert result["future_real_send_eligible_after_exact_phrase"] is True


def test_future_confirmation_phrase_is_present_inactive_and_non_executable(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

    assert payload["future_confirmation_phrase_required"] == FUTURE_CONFIRMATION_PHRASE
    assert payload["future_confirmation_phrase_active"] is False
    assert payload["future_confirmation_phrase_executable"] is False
    assert payload["future_confirmation_inactive_passed"] is True
    for result in payload["scenario_results"]:
        assert result["future_confirmation_phrase_required"] == FUTURE_CONFIRMATION_PHRASE
        assert result["future_confirmation_phrase_active"] is False
        assert result["future_confirmation_phrase_executable"] is False


def test_no_real_telegram_send_called(tmp_path: Path) -> None:
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = _drill(tmp_path, env=_env())

    urlopen.assert_not_called()
    assert payload["no_real_telegram_send_passed"] is True
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_no_telegram_send_called(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    for result in payload["scenario_results"]:
        assert result["telegram_send_called"] is False
        assert result["telegram_message_sent"] is False


def test_would_send_real_telegram_now_false(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

    assert payload["would_send_real_telegram_now"] is False
    for result in payload["scenario_results"]:
        assert result["would_send_real_telegram_now"] is False


def test_secrets_are_masked_only(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())
    readiness = payload["telegram_config_readiness"]

    assert readiness["telegram_token_preview"] == "1234...wxyz"
    assert readiness["telegram_chat_id_preview"] == "-100...7890"
    assert payload["secrets_shown"] is False
    assert payload["no_secret_leak_passed"] is True


def test_full_token_and_chat_id_never_appear_in_json_or_text(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())
    combined = "\n".join(
        [
            json.dumps(payload, sort_keys=True),
            format_synthetic_send_drill_json(payload),
            format_synthetic_send_drill_text(payload),
        ]
    )

    assert RAW_TOKEN not in combined
    assert RAW_CHAT_ID not in combined


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _drill(tmp_path, env=_env(), write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_no_env_mutation(tmp_path: Path) -> None:
    before = dict(os.environ)
    payload = _drill(tmp_path, env=_env())

    assert dict(os.environ) == before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

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
        payload = _drill(tmp_path, env=_env())

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    assert _drill(tmp_path, env=_env())["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    assert _drill(tmp_path, env=_env())["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _drill(tmp_path, env=_env())

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
            "real-telegram-observation-alert-synthetic-send-drill-preview",
            "--no-write",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", **_env()},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["drill_status"] == DRILL_PASSED
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_previews_only(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r320_real_telegram_observation_alert_synthetic_send_drill_preview.sh"
    script_text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "--apply" not in script_text
    assert "--send" not in script_text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs"), **_env()},
        text=True,
        capture_output=True,
        check=True,
    )

    for section in (
        "R320 REAL TELEGRAM OBSERVATION ALERT SYNTHETIC SEND DRILL PREVIEW",
        "TELEGRAM CREDENTIAL READINESS",
        "DRILL STATUS",
        "SCENARIOS RUN",
        "HEALTHY NO-HEARTBEAT RESULT",
        "SYNTHETIC STALE OBSERVATION RESULT",
        "SYNTHETIC FINAL SAFETY VIOLATION RESULT",
        "FUTURE CONFIRMATION PHRASE STATUS",
        "REAL SEND PREVIEW FLAGS",
        "SAFETY FLAGS",
        "RECOMMENDED NEXT PHASE",
    ):
        assert section in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert RAW_TOKEN not in result.stdout
    assert RAW_CHAT_ID not in result.stdout


def test_r319_r318_r317_r316_r315_r314_compatibility_remains_intact(tmp_path: Path) -> None:
    health = build_synthetic_health_panel(
        scenario_name="stale_observation",
        now=NOW,
        max_age_seconds=180,
    )
    r315_preview = _result(
        _drill(tmp_path, scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION, env=_env()),
        SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    )["source_alert_preview"]
    r316_gate = build_multi_lane_observation_alert_send_gate(
        log_dir=tmp_path,
        apply=False,
        alert_preview=r315_preview,
        write=False,
        no_write=True,
        now=NOW,
    )
    r318_preview = build_real_telegram_observation_alert_send_preview(
        log_dir=tmp_path,
        env=_env(),
        alert_preview=r315_preview,
        write=False,
        no_write=True,
        now=NOW,
    )

    assert health["event_type"] == "R314_MULTI_LANE_OBSERVATION_HEALTH_PANEL"
    assert r315_preview["event_type"] == "R315_MULTI_LANE_OBSERVATION_ALERTING_PREVIEW"
    assert r316_gate["event_type"] == "R316_HUMAN_REVIEWED_OBSERVATION_ALERT_SEND_GATE"
    assert r315_preview["source_health_panel"]["synthetic_scenario"] is True
    assert r318_preview["event_type"] == "R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW"
    assert r318_preview["telegram_config_readiness"]["telegram_config_valid_for_future_send"] is True


def _drill(
    tmp_path: Path,
    *,
    scenario: str = "all",
    env: dict[str, str] | None = None,
    env_file_path: str | Path | None = None,
    write: bool = False,
) -> dict[str, object]:
    return build_real_telegram_observation_alert_synthetic_send_drill_preview(
        log_dir=tmp_path,
        scenario=scenario,
        env=env if env is not None else _env(),
        env_file_path=env_file_path,
        write=write,
        no_write=not write,
        now=NOW,
    )


def _result(payload: dict[str, object], scenario_name: str) -> dict[str, object]:
    for result in payload["scenario_results"]:  # type: ignore[index]
        if result["scenario_name"] == scenario_name:
            return result
    raise AssertionError(f"missing scenario result {scenario_name}")


def _env() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID}


def _write_env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "notifications.env"
    env_file.write_text(
        f"TELEGRAM_BOT_TOKEN='{RAW_TOKEN}'\nTELEGRAM_CHAT_ID=\"{RAW_CHAT_ID}\"\n",
        encoding="utf-8",
    )
    return env_file
