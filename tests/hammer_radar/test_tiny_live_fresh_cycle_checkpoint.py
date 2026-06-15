from __future__ import annotations

import hmac
import json
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_fresh_cycle_checkpoint import (
    CONFIRM_TINY_LIVE_FRESH_CYCLE_CHECKPOINT_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY,
    TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED,
    TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED,
    build_tiny_live_fresh_cycle_checkpoint,
    load_tiny_live_fresh_cycle_checkpoint_records,
)
from src.app.hammer_radar.operator.tiny_live_manual_submit_checkpoint import (
    CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE,
    build_tiny_live_manual_submit_checkpoint,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    OVERRIDE_ENV_NAME,
)
from tests.hammer_radar.test_tiny_live_fresh_context_signed_request_regeneration_gate import (
    API_KEY,
    API_SECRET,
    _clean_env,
)
from tests.hammer_radar.test_tiny_live_manual_submit_checkpoint import _fixture_r258
from tests.hammer_radar.test_tiny_live_submit_gate_preview import NOW

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, external = _fixture_r259(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-fresh-cycle-checkpoint",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_FRESH_CYCLE_CHECKPOINT_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["target_scope"]["fresh_cycle_checkpoint_only"] is True
    assert payload["fresh_cycle_checkpoint_recorded"] is False
    assert payload["safety"]["network_allowed"] is False
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger_and_makes_no_network_signing_submit_or_order_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r259(tmp_path, monkeypatch)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_fresh_cycle_checkpoint(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert payload["fresh_cycle_checkpoint_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_fresh_cycle_safety(payload)
    _assert_no_secret_values(payload)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r259(tmp_path, monkeypatch)

    payload = build_tiny_live_fresh_cycle_checkpoint(
        log_dir=log_dir,
        record_fresh_cycle_checkpoint=True,
        confirm_tiny_live_fresh_cycle_checkpoint="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_FRESH_CYCLE_CHECKPOINT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["fresh_cycle_checkpoint_recorded"] is False
    assert payload["fresh_cycle_checkpoint_overall_status"] == (
        "TINY_LIVE_FRESH_CYCLE_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_fresh_cycle_safety(payload)


def test_exact_confirmation_records_checkpoint_only(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r259(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_fresh_cycle_checkpoint(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            record_fresh_cycle_checkpoint=True,
            confirm_tiny_live_fresh_cycle_checkpoint=(
                CONFIRM_TINY_LIVE_FRESH_CYCLE_CHECKPOINT_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_FRESH_CYCLE_CHECKPOINT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["fresh_cycle_checkpoint_recorded"] is True
    assert payload["fresh_cycle_checkpoint_overall_status"] == (
        "TINY_LIVE_FRESH_CYCLE_RECORDED_REFRESH_REQUIRED"
    )
    records = load_tiny_live_fresh_cycle_checkpoint_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    raw = (log_dir / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw
    assert API_SECRET not in raw
    _assert_fresh_cycle_safety(payload)
    _assert_no_secret_values(payload)


def test_summarizes_r258_blockers_and_detects_r253_next_when_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r259(tmp_path, monkeypatch)

    payload = build_tiny_live_fresh_cycle_checkpoint(log_dir=log_dir, now=NOW)

    assert payload["input_summary"] == {
        "r258_manual_checkpoint_found": True,
        "r258_manual_checkpoint_valid": True,
        "r257_final_arming_found": True,
        "r256_runbook_found": True,
        "r255_actual_submit_gate_found": True,
        "r254_submit_gate_preview_found": True,
        "r253b_fresh_regeneration_found": True,
        "r253_final_readonly_found": True,
    }
    blockers = payload["fresh_cycle_blockers"]
    assert "signed_request_timestamp_stale" in blockers["blocked_by"]
    assert "live_execution_not_enabled" in blockers["blocked_by"]
    assert "risk_contract_invalid" in blockers["blocked_by"]
    assert blockers["timestamp_stale"] is True
    assert blockers["live_controls_not_armed"] is True
    assert blockers["live_execution_not_enabled"] is True
    assert blockers["manual_decision_required"] is True
    assert blockers["submit_allowed_now"] is False

    statuses = payload["fresh_cycle_step_statuses"]
    assert statuses["r253_final_readonly_refresh"] == {
        "available": True,
        "fresh_enough": False,
        "required_next": True,
    }
    assert statuses["r253b_fresh_signed_regeneration"]["fresh_enough"] is False
    assert statuses["r253b_fresh_signed_regeneration"]["required_next"] is False
    assert statuses["r258_manual_checkpoint_recheck"] == {
        "available": True,
        "required_after_fresh_cycle": True,
    }


def test_command_templates_go_no_go_matrix_and_no_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r259(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_fresh_cycle_checkpoint(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane

    commands = payload["fresh_cycle_command_templates"]
    assert "tiny-live-final-readonly-mark-price-refresh-gate" in commands["r253_readonly_refresh_command"]
    assert "tiny-live-fresh-context-signed-request-regeneration-gate" in commands["r253b_regeneration_command"]
    assert "tiny-live-submit-gate-preview" in commands["r254_submit_gate_preview_command"]
    assert "tiny-live-actual-submit-gate" in commands["r255_dry_preview_command"]
    assert "tiny-live-manual-submit-checkpoint" in commands["r258_recheck_command"]
    assert commands["commands_are_templates_only"] is True
    assert commands["must_not_auto_run"] is True

    packet = payload["fresh_cycle_go_no_go_packet"]
    assert packet["go_for_manual_submit_now"] is False
    assert packet["go_for_fresh_cycle_now"] is True
    assert packet["next_required_step"] == "RUN_R253_READONLY_REFRESH"
    assert packet["operator_should_submit_now"] is False
    assert packet["operator_should_arm_live_controls_manually"] is True
    assert packet["operator_should_run_fresh_cycle"] is True

    matrix = payload["fresh_cycle_checkpoint_matrix"]
    assert matrix["r258_available"] is True
    assert matrix["fresh_cycle_required"] is True
    assert matrix["fresh_cycle_next_step_known"] is True
    assert matrix["command_templates_ready"] is True
    assert matrix["record_confirmed"] is False
    assert matrix["recorded"] is False
    assert matrix["submit_allowed"] is False
    assert matrix["order_placed"] is False
    assert matrix["blocked_by"] == packet_blockers(payload)

    assert payload["fresh_cycle_checkpoint_overall_status"] == (
        "TINY_LIVE_FRESH_CYCLE_READY_FOR_RECORDING"
    )
    assert payload["recommended_next_operator_move"] == (
        "Run R253 final readonly refresh first."
    )
    assert payload["recommended_next_engineering_move"] == (
        "Operator should run the next fresh-cycle command manually; do not submit or call Binance from R259."
    )
    assert payload["do_not_run_yet"] == [
        "real submit before fresh cycle",
        "real submit before R255 dry preview",
        "real submit while live controls are not intentionally armed",
        "duplicate live submit",
        "manual submit while blockers remain",
    ]
    _assert_fresh_cycle_safety(payload)
    _assert_no_secret_values(payload)


def packet_blockers(payload: Mapping[str, object]) -> list[str]:
    blockers = payload["fresh_cycle_blockers"]
    assert isinstance(blockers, Mapping)
    return list(blockers["blocked_by"])


def _fixture_r259(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, Path]:
    log_dir, risk_path, lane_path, external = _fixture_r258(tmp_path, monkeypatch)
    r258 = build_tiny_live_manual_submit_checkpoint(
        log_dir=log_dir,
        record_manual_submit_checkpoint=True,
        confirm_tiny_live_manual_submit_checkpoint=(
            CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE
        ),
        now=NOW + timedelta(minutes=10),
    )
    assert r258["manual_submit_checkpoint_recorded"] is True
    return log_dir, risk_path, lane_path, external


def _assert_fresh_cycle_safety(payload: Mapping[str, object]) -> None:
    safety = payload["safety"]
    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "hmac_signature_created",
        "signed_request_written",
        "signed_order_request_created",
        "signed_trading_request_created",
        "submit_allowed",
        "submit_attempted",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "private_binance_endpoint_called",
        "signed_binance_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "live_controls_armed_by_phase",
        "secrets_read",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["fresh_cycle_checkpoint_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
