from __future__ import annotations

import hmac
import json
import subprocess
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_final_pre_submit_arming_drill import (
    CONFIRM_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_PHRASE,
    build_tiny_live_final_pre_submit_arming_drill,
)
from src.app.hammer_radar.operator.tiny_live_manual_submit_checkpoint import (
    CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY,
    TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED,
    TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED,
    build_tiny_live_manual_submit_checkpoint,
    load_tiny_live_manual_submit_checkpoint_records,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    OVERRIDE_ENV_NAME,
)
from tests.hammer_radar.test_tiny_live_final_pre_submit_arming_drill import _fixture_r257
from tests.hammer_radar.test_tiny_live_fresh_context_signed_request_regeneration_gate import (
    API_KEY,
    API_SECRET,
    _clean_env,
)
from tests.hammer_radar.test_tiny_live_submit_gate_preview import NOW

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, external = _fixture_r258(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-manual-submit-checkpoint",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["target_scope"]["manual_submit_checkpoint_only"] is True
    assert payload["manual_submit_checkpoint_recorded"] is False
    assert payload["safety"]["network_allowed"] is False
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger_and_makes_no_network_signing_submit_or_order_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r258(tmp_path, monkeypatch)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_manual_submit_checkpoint(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert payload["manual_submit_checkpoint_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_checkpoint_safety(payload)
    _assert_no_secret_values(payload)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r258(tmp_path, monkeypatch)

    payload = build_tiny_live_manual_submit_checkpoint(
        log_dir=log_dir,
        record_manual_submit_checkpoint=True,
        confirm_tiny_live_manual_submit_checkpoint="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["manual_submit_checkpoint_recorded"] is False
    assert payload["manual_submit_checkpoint_overall_status"] == (
        "TINY_LIVE_MANUAL_CHECKPOINT_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_checkpoint_safety(payload)


def test_exact_confirmation_records_checkpoint_only(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r258(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_manual_submit_checkpoint(
            log_dir=log_dir,
            record_manual_submit_checkpoint=True,
            confirm_tiny_live_manual_submit_checkpoint=(
                CONFIRM_TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_MANUAL_SUBMIT_CHECKPOINT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["manual_submit_checkpoint_recorded"] is True
    assert payload["manual_submit_checkpoint_overall_status"] == (
        "TINY_LIVE_MANUAL_CHECKPOINT_RECORDED_FRESH_CYCLE_REQUIRED"
    )
    records = load_tiny_live_manual_submit_checkpoint_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    raw = (log_dir / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw
    assert API_SECRET not in raw
    _assert_checkpoint_safety(payload)
    _assert_no_secret_values(payload)


def test_summarizes_inputs_blockers_fresh_cycle_and_live_controls(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r258(tmp_path, monkeypatch)

    payload = build_tiny_live_manual_submit_checkpoint(log_dir=log_dir, now=NOW)

    assert payload["input_summary"] == {
        "r257_final_arming_drill_found": True,
        "r257_final_arming_drill_valid": True,
        "r256_operator_runbook_found": True,
        "r255_actual_submit_gate_found": True,
        "r254_submit_gate_preview_found": True,
        "r253b_fresh_regeneration_found": True,
    }
    blockers = payload["manual_submit_blocker_summary"]
    assert blockers["blocked_by"] == [
        "signed_request_timestamp_stale",
        "official_lane_not_tiny_live",
        "live_execution_not_enabled",
    ]
    assert blockers["submit_allowed_now"] is False
    assert blockers["operator_should_not_submit_now"] is True
    assert blockers["fresh_cycle_required"] is True
    assert blockers["live_controls_manual_review_required"] is True
    assert blockers["manual_decision_required"] is True

    fresh = payload["fresh_cycle_requirement"]
    assert fresh["required_now"] is True
    assert fresh["reason"] == "timestamp_stale"
    assert fresh["sequence"] == [
        "R253 final readonly refresh",
        "R253B fresh signed request regeneration",
        "R254 submit gate preview",
        "R255 dry preview",
        "R258 manual checkpoint re-check",
    ]
    assert fresh["r259_future_phase"] == "R259_TINY_LIVE_FRESH_CYCLE_CHECKPOINT"

    controls = payload["live_controls_checkpoint"]
    assert controls["live_execution_enabled"] is False
    assert controls["official_lane_allowed"] is False
    assert controls["kill_switch_allows_tiny_live"] is False
    assert controls["manual_arming_required"] is True
    assert controls["auto_armed_by_this_phase"] is False


def test_command_reconciliation_go_no_go_matrix_and_mutation_safety(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r258(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_manual_submit_checkpoint(log_dir=log_dir, now=NOW)

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane

    command = payload["real_submit_command_checkpoint"]
    assert command["template_available"] is True
    assert command["must_not_auto_run"] is True
    assert command["requires_manual_operator_paste"] is True
    assert command["contains_execute_flag"] is True
    assert command["contains_allow_real_endpoint_flag"] is True
    assert command["contains_exact_confirmation_phrase"] is True

    reconciliation = payload["reconciliation_checkpoint"]
    assert reconciliation == {
        "post_submit_reconciliation_ready": True,
        "partial_success_plan_ready": True,
        "abort_cleanup_ready": True,
        "duplicate_submit_protection_ready": True,
    }

    packet = payload["manual_submit_go_no_go_packet"]
    assert packet["go_for_manual_submit_now"] is False
    assert packet["no_go_reasons"] == [
        "signed_request_timestamp_stale",
        "official_lane_not_tiny_live",
        "live_execution_not_enabled",
    ]
    assert packet["operator_should_regenerate_first"] is True
    assert packet["operator_should_arm_live_controls_manually"] is True
    assert packet["operator_should_run_r255_dry_preview"] is True
    assert packet["operator_should_review_reconciliation"] is True
    assert packet["operator_should_submit_now"] is False
    assert packet["next_required_human_action"] == "RUN_FRESH_CYCLE"

    matrix = payload["manual_submit_checkpoint_matrix"]
    assert matrix["r257_available"] is True
    assert matrix["fresh_cycle_requirement_known"] is True
    assert matrix["live_controls_state_known"] is True
    assert matrix["submit_command_known"] is True
    assert matrix["reconciliation_ready"] is True
    assert matrix["record_confirmed"] is False
    assert matrix["recorded"] is False
    assert matrix["submit_allowed"] is False
    assert matrix["order_placed"] is False
    assert matrix["blocked_by"] == packet["no_go_reasons"]

    assert payload["manual_submit_checkpoint_overall_status"] == (
        "TINY_LIVE_MANUAL_CHECKPOINT_READY_FOR_RECORDING"
    )
    assert payload["recommended_next_operator_move"] == "RUN_FRESH_CYCLE"
    assert payload["recommended_next_engineering_move"] == (
        "Create R259 fresh-cycle checkpoint; still no submit or Binance call."
    )
    assert payload["do_not_run_yet"] == [
        "real submit without fresh cycle",
        "real submit without manual live-control arming review",
        "real submit without R255 dry preview",
        "duplicate live submit",
        "manual submit while blockers remain",
    ]
    _assert_checkpoint_safety(payload)
    _assert_no_secret_values(payload)


def _fixture_r258(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, Path]:
    log_dir, risk_path, lane_path, external = _fixture_r257(tmp_path, monkeypatch)
    r257 = build_tiny_live_final_pre_submit_arming_drill(
        log_dir=log_dir,
        record_final_pre_submit_arming_drill=True,
        confirm_tiny_live_final_pre_submit_arming_drill=(
            CONFIRM_TINY_LIVE_FINAL_PRE_SUBMIT_ARMING_DRILL_PHRASE
        ),
        now=NOW,
    )
    assert r257["final_pre_submit_arming_drill_recorded"] is True
    return log_dir, risk_path, lane_path, external


def _assert_checkpoint_safety(payload: Mapping[str, object]) -> None:
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
    assert safety["manual_submit_checkpoint_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
