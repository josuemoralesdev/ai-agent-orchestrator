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
from src.app.hammer_radar.operator.observation_alert_send_gate_operator_drill import (
    build_synthetic_health_panel,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_send_preview import (
    FUTURE_CONFIRMATION_PHRASE,
    build_real_telegram_observation_alert_send_preview,
)
from src.app.hammer_radar.operator.real_telegram_observation_alert_synthetic_send_drill_preview import (
    build_real_telegram_observation_alert_synthetic_send_drill_preview,
)
from src.app.hammer_radar.operator.real_telegram_synthetic_alert_send_apply_gate import (
    EVENT_TYPE,
    LEDGER_FILENAME,
    SCENARIO_HEALTHY,
    SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
    SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED,
    SEND_GATE_BLOCKED_CREDENTIALS_REQUIRED,
    SEND_GATE_BLOCKED_NO_ALERT_REQUIRED,
    SEND_GATE_MOCK_SENT,
    SEND_GATE_PREVIEW_READY,
    SEND_GATE_REAL_SEND_DISABLED_IN_CODEX,
    build_real_telegram_synthetic_alert_send_apply_gate,
    format_real_telegram_synthetic_alert_send_apply_gate_json,
    format_real_telegram_synthetic_alert_send_apply_gate_text,
)

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_TOKEN = "1234:abcdefghijklmnopqrstuvwxyz"
RAW_CHAT_ID = "-1001234567890"


def test_default_preview_does_not_send(tmp_path: Path) -> None:
    payload = _gate(tmp_path)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["send_gate_status"] == SEND_GATE_PREVIEW_READY
    assert payload["apply_requested"] is False
    assert payload["confirmation_phrase_matched"] is False
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    assert payload["would_send_real_telegram_now"] is False
    assert payload["real_send_preview_only"] is True


def test_missing_confirmation_blocks_apply(tmp_path: Path) -> None:
    payload = _gate(tmp_path, apply=True, confirmation=None)

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    assert payload["apply_requested"] is True
    assert payload["confirmation_phrase_matched"] is False
    assert "confirmation_phrase_required" in payload["send_blockers"]
    _assert_no_send(payload)


def test_wrong_confirmation_blocks_apply(tmp_path: Path) -> None:
    payload = _gate(tmp_path, apply=True, confirmation="WRONG PHRASE")

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_CONFIRMATION_REQUIRED
    assert payload["confirmation_phrase_matched"] is False
    assert "confirmation_phrase_required" in payload["send_blockers"]
    _assert_no_send(payload)


def test_healthy_scenario_with_exact_phrase_blocks_no_alert_send(tmp_path: Path) -> None:
    payload = _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, scenario=SCENARIO_HEALTHY)

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_NO_ALERT_REQUIRED
    assert payload["confirmation_phrase_matched"] is True
    assert payload["alert_required"] is False
    assert "alert_required_false" in payload["send_blockers"]
    _assert_no_send(payload)


def test_synthetic_stale_scenario_with_exact_phrase_and_mock_records_mock_send_only(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        telegram_sender_mode="mock",
    )

    assert payload["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert payload["credentials_ready"] is True
    assert payload["alert_required"] is True
    assert payload["telegram_sender_mode"] == "mock"
    assert payload["telegram_send_called"] is True
    assert payload["telegram_message_sent"] is True
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_synthetic_final_safety_scenario_with_exact_phrase_and_mock_records_mock_send_only(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
        telegram_sender_mode="mock",
    )

    assert payload["send_gate_status"] == SEND_GATE_MOCK_SENT
    assert payload["alert_required"] is True
    assert payload["alert_severity"] == "CRITICAL_PREVIEW_NO_SEND"
    assert payload["telegram_send_called"] is True
    assert payload["telegram_message_sent"] is True
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_synthetic_stale_scenario_with_exact_phrase_and_real_disabled_blocks_real_send(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        telegram_sender_mode="real-disabled",
    )

    assert payload["send_gate_status"] == SEND_GATE_REAL_SEND_DISABLED_IN_CODEX
    assert payload["telegram_sender_mode"] == "real-disabled"
    assert "real_send_disabled_in_codex" in payload["send_blockers"]
    _assert_no_send(payload)


def test_synthetic_final_safety_scenario_with_exact_phrase_and_real_disabled_blocks_real_send(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        scenario=SCENARIO_SYNTHETIC_FINAL_SAFETY_VIOLATION,
        telegram_sender_mode="real-disabled",
    )

    assert payload["send_gate_status"] == SEND_GATE_REAL_SEND_DISABLED_IN_CODEX
    assert payload["alert_required"] is True
    _assert_no_send(payload)


def test_credentials_loaded_from_injected_env(tmp_path: Path) -> None:
    payload = _gate(tmp_path, env=_env())

    assert payload["credentials_ready"] is True
    assert payload["telegram_config_readiness"]["telegram_config_source_kind"] == "env"
    assert payload["telegram_config_readiness"]["telegram_config_valid_for_future_send"] is True


def test_credentials_loaded_from_injected_private_env_file_fallback(tmp_path: Path) -> None:
    env_file = _write_env_file(tmp_path)
    payload = _gate(tmp_path, env={}, env_file_path=env_file)

    assert payload["credentials_ready"] is True
    assert payload["telegram_config_readiness"]["telegram_config_source_kind"] == "private_env_file"
    assert payload["telegram_config_readiness"]["telegram_config_source_path"] == str(env_file)


def test_missing_credentials_block_apply(tmp_path: Path) -> None:
    payload = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        env={},
        env_file_path=tmp_path / "missing.env",
    )

    assert payload["send_gate_status"] == SEND_GATE_BLOCKED_CREDENTIALS_REQUIRED
    assert payload["credentials_ready"] is False
    assert "telegram_credentials_required" in payload["send_blockers"]
    _assert_no_send(payload)


def test_secrets_masked_only(tmp_path: Path) -> None:
    payload = _gate(tmp_path)
    readiness = payload["telegram_config_readiness"]

    assert readiness["telegram_token_preview"] == "1234...wxyz"
    assert readiness["telegram_chat_id_preview"] == "-100...7890"
    assert payload["secrets_shown"] is False
    assert payload["no_secret_leak_passed"] is True


def test_full_token_and_chat_id_never_appear_in_json_or_text(tmp_path: Path) -> None:
    payload = _gate(tmp_path)
    combined = "\n".join(
        [
            json.dumps(payload, sort_keys=True),
            format_real_telegram_synthetic_alert_send_apply_gate_json(payload),
            format_real_telegram_synthetic_alert_send_apply_gate_text(payload),
        ]
    )

    assert RAW_TOKEN not in combined
    assert RAW_CHAT_ID not in combined


def test_real_telegram_send_called_false_in_every_codex_validation_path(tmp_path: Path) -> None:
    for payload in _validation_paths(tmp_path):
        assert payload["real_telegram_send_called"] is False


def test_real_telegram_message_sent_false_in_every_codex_validation_path(tmp_path: Path) -> None:
    for payload in _validation_paths(tmp_path):
        assert payload["real_telegram_message_sent"] is False


def test_telegram_send_called_false_by_default_and_true_only_in_mock_apply_paths(tmp_path: Path) -> None:
    default = _gate(tmp_path)
    mock = _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, telegram_sender_mode="mock")
    real_disabled = _gate(
        tmp_path,
        apply=True,
        confirmation=FUTURE_CONFIRMATION_PHRASE,
        telegram_sender_mode="real-disabled",
    )

    assert default["telegram_send_called"] is False
    assert mock["telegram_send_called"] is True
    assert real_disabled["telegram_send_called"] is False


def test_no_config_mutation(tmp_path: Path) -> None:
    risk_path = REPO_ROOT / "configs/hammer_radar/tiny_live_risk_contracts.json"
    arming_path = REPO_ROOT / "configs/hammer_radar/autonomous_arming_state.json"
    risk_before = risk_path.read_text(encoding="utf-8")
    arming_before = arming_path.read_text(encoding="utf-8")

    payload = _gate(tmp_path, write=True)

    assert risk_path.read_text(encoding="utf-8") == risk_before
    assert arming_path.read_text(encoding="utf-8") == arming_before
    assert payload["config_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert (tmp_path / LEDGER_FILENAME).exists()


def test_no_env_mutation(tmp_path: Path) -> None:
    before = dict(os.environ)
    payload = _gate(tmp_path)

    assert dict(os.environ) == before
    assert payload["env_written"] is False
    assert payload["env_mutated"] is False


def test_no_arming_mutation(tmp_path: Path) -> None:
    payload = _gate(tmp_path)

    assert payload["autonomous_arming_state_changed"] is False
    assert payload["global_live_flags_changed"] is False


def test_no_systemd_mutation(tmp_path: Path) -> None:
    payload = _gate(tmp_path)

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
        payload = _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, telegram_sender_mode="mock")

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    preview_payload.assert_not_called()
    signed_order.assert_not_called()
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False


def test_no_submit(tmp_path: Path) -> None:
    assert _gate(tmp_path)["submit_allowed"] is False


def test_no_final_command(tmp_path: Path) -> None:
    assert _gate(tmp_path)["final_command_available"] is False


def test_no_binance_endpoint(tmp_path: Path) -> None:
    payload = _gate(tmp_path)

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
            "real-telegram-synthetic-alert-send-apply-gate",
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
    assert payload["send_gate_status"] == SEND_GATE_PREVIEW_READY
    assert payload["real_telegram_send_called"] is False


def test_operator_script_exists_and_previews_only(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r321_real_telegram_synthetic_alert_send_apply_gate.sh"
    script_text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "--apply" not in script_text
    assert "real-disabled" not in script_text
    result = subprocess.run(
        ["bash", str(script.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs"), **_env()},
        text=True,
        capture_output=True,
        check=True,
    )

    for section in (
        "R321 HUMAN-REVIEWED REAL TELEGRAM SYNTHETIC ALERT SEND APPLY GATE",
        "SCENARIO",
        "APPLY / CONFIRMATION STATUS",
        "TELEGRAM CREDENTIAL READINESS",
        "ALERT SUMMARY",
        "SEND GATE STATUS",
        "MOCK/REAL SEND FLAGS",
        "SAFETY FLAGS",
        "RECOMMENDED NEXT PHASE",
    ):
        assert section in result.stdout
    assert "apply_requested: False" in result.stdout
    assert "real_telegram_send_called: False" in result.stdout
    assert RAW_TOKEN not in result.stdout
    assert RAW_CHAT_ID not in result.stdout


def test_r320_r319_r318_r317_r316_r315_r314_compatibility_remains_intact(tmp_path: Path) -> None:
    r321_payload = _gate(tmp_path)
    r320_payload = build_real_telegram_observation_alert_synthetic_send_drill_preview(
        log_dir=tmp_path,
        scenario=SCENARIO_SYNTHETIC_STALE_OBSERVATION,
        env=_env(),
        write=False,
        no_write=True,
        now=NOW,
    )
    health = build_synthetic_health_panel(
        scenario_name="stale_observation",
        now=NOW,
        max_age_seconds=180,
    )
    r315_preview = r321_payload["source_alert_preview"]
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
    assert r318_preview["event_type"] == "R318_REAL_TELEGRAM_ALERT_SEND_GATE_PREVIEW"
    assert r320_payload["event_type"] == "R320_REAL_TELEGRAM_OBSERVATION_ALERT_SYNTHETIC_SEND_DRILL_PREVIEW"
    assert r321_payload["event_type"] == EVENT_TYPE


def _gate(
    tmp_path: Path,
    *,
    apply: bool = False,
    confirmation: str | None = None,
    scenario: str = SCENARIO_SYNTHETIC_STALE_OBSERVATION,
    telegram_sender_mode: str = "mock",
    env: dict[str, str] | None = None,
    env_file_path: str | Path | None = None,
    write: bool = False,
) -> dict[str, object]:
    return build_real_telegram_synthetic_alert_send_apply_gate(
        log_dir=tmp_path,
        apply=apply,
        confirmation=confirmation,
        scenario=scenario,
        telegram_sender_mode=telegram_sender_mode,
        env=env if env is not None else _env(),
        env_file_path=env_file_path,
        write=write,
        no_write=not write,
        now=NOW,
    )


def _validation_paths(tmp_path: Path) -> list[dict[str, object]]:
    return [
        _gate(tmp_path),
        _gate(tmp_path, apply=True),
        _gate(tmp_path, apply=True, confirmation="WRONG PHRASE"),
        _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, scenario=SCENARIO_HEALTHY),
        _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, telegram_sender_mode="mock"),
        _gate(tmp_path, apply=True, confirmation=FUTURE_CONFIRMATION_PHRASE, telegram_sender_mode="real-disabled"),
    ]


def _assert_no_send(payload: dict[str, object]) -> None:
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False
    assert payload["would_send_real_telegram_now"] is False


def _env() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": RAW_TOKEN, "TELEGRAM_CHAT_ID": RAW_CHAT_ID}


def _write_env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "notifications.env"
    env_file.write_text(
        f"TELEGRAM_BOT_TOKEN='{RAW_TOKEN}'\nTELEGRAM_CHAT_ID=\"{RAW_CHAT_ID}\"\n",
        encoding="utf-8",
    )
    return env_file
