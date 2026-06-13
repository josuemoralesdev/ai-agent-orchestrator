from __future__ import annotations

import hmac
import json
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    DRY_PREVIEW_CONFIRMATION_PHRASE,
    REAL_SUBMIT_CONFIRMATION_PHRASE,
    build_tiny_live_actual_submit_gate,
)
from src.app.hammer_radar.operator.tiny_live_operator_real_submit_runbook import (
    CONFIRM_TINY_LIVE_OPERATOR_RUNBOOK_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY,
    TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED,
    TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED,
    build_tiny_live_operator_real_submit_runbook,
    load_tiny_live_operator_real_submit_runbook_records,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    OVERRIDE_ENV_NAME,
)
from tests.hammer_radar.test_tiny_live_fresh_context_signed_request_regeneration_gate import (
    API_KEY,
    API_SECRET,
    _clean_env,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
    build_tiny_live_submit_gate_preview,
)
from tests.hammer_radar.test_tiny_live_submit_gate_preview import NOW, _fixture_r254

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, external = _fixture_r256(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-operator-real-submit-runbook",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["target_scope"]["operator_runbook_only"] is True
    assert payload["operator_runbook_recorded"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger_and_makes_no_network_or_signing_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r256(tmp_path, monkeypatch)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_operator_real_submit_runbook(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert payload["operator_runbook_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_runbook_safety(payload)
    _assert_no_secret_values(payload)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r256(tmp_path, monkeypatch)

    payload = build_tiny_live_operator_real_submit_runbook(
        log_dir=log_dir,
        record_operator_real_submit_runbook=True,
        confirm_tiny_live_operator_runbook="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["operator_runbook_recorded"] is False
    assert payload["operator_runbook_overall_status"] == "TINY_LIVE_OPERATOR_RUNBOOK_REJECTED_BAD_CONFIRMATION"
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_runbook_safety(payload)


def test_exact_confirmation_records_runbook_only(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r256(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_operator_real_submit_runbook(
            log_dir=log_dir,
            record_operator_real_submit_runbook=True,
            confirm_tiny_live_operator_runbook=CONFIRM_TINY_LIVE_OPERATOR_RUNBOOK_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_OPERATOR_REAL_SUBMIT_RUNBOOK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["operator_runbook_recorded"] is True
    assert payload["operator_runbook_overall_status"] == (
        "TINY_LIVE_OPERATOR_RUNBOOK_RECORDED_MANUAL_DECISION_REQUIRED"
    )
    records = load_tiny_live_operator_real_submit_runbook_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    _assert_runbook_safety(payload)
    _assert_no_secret_values(payload)
    raw = (log_dir / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw
    assert API_SECRET not in raw


def test_output_includes_required_operator_controls(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r256(tmp_path, monkeypatch)

    payload = build_tiny_live_operator_real_submit_runbook(log_dir=log_dir, now=NOW)

    command = payload["real_submit_command_template"]["command"]
    checklist = " ".join(payload["operator_pre_submit_checklist"]).lower()
    partial = payload["partial_success_handling_plan"]
    abort_tree = payload["abort_cleanup_decision_tree"]

    assert "--execute-actual-submit" in command
    assert "--allow-real-binance-order-endpoint" in command
    assert payload["real_submit_command_template"]["confirmation_phrase"] == REAL_SUBMIT_CONFIRMATION_PHRASE
    assert REAL_SUBMIT_CONFIRMATION_PHRASE in command
    assert "regenerate" in checklist
    assert "controls are intentionally armed" in checklist
    assert "idempotency" in checklist
    assert "reconciliation" in checklist
    assert "if_main_succeeds_stop_fails" in partial
    assert partial["if_main_succeeds_stop_fails"]
    assert "if_unknown_exchange_response" in partial
    assert partial["if_unknown_exchange_response"]
    assert abort_tree["before_submit"]
    assert payload["post_submit_reconciliation_checklist"] == [
        "record exchange order ids",
        "verify main order status",
        "verify stop reduceOnly order status",
        "verify take-profit reduceOnly order status",
        "verify no extra orders",
        "verify live execution ledger append",
        "verify idempotency key recorded",
    ]


def test_current_blockers_and_decision_packet_reflect_r255(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r256(tmp_path, monkeypatch)

    payload = build_tiny_live_operator_real_submit_runbook(log_dir=log_dir, now=NOW)

    blockers = payload["current_submit_blockers"]
    assert blockers["blocked_by"] == [
        "signed_request_timestamp_stale",
        "official_lane_not_tiny_live",
        "live_execution_not_enabled",
    ]
    assert blockers["requires_regeneration"] is True
    assert blockers["requires_live_controls_arming"] is True
    assert blockers["submit_allowed_now"] is False
    assert payload["operator_manual_decision_packet"]["operator_should_submit_now"] is False
    assert payload["operator_manual_decision_packet"]["operator_should_regenerate_first"] is True
    assert payload["operator_manual_decision_packet"]["operator_should_arm_live_controls_manually"] is True
    assert payload["operator_manual_decision_packet"]["next_required_human_action"] == "REGENERATE_SIGNED_REQUEST"
    assert payload["runbook_gate_matrix"]["submit_allowed"] is False
    assert payload["runbook_gate_matrix"]["order_placed"] is False


def test_duplicate_review_uses_r255_idempotency_summary(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r256(tmp_path, monkeypatch)

    payload = build_tiny_live_operator_real_submit_runbook(log_dir=log_dir, now=NOW)

    duplicate = payload["duplicate_submit_protection_review"]
    assert duplicate["idempotency_key_required"] is True
    assert duplicate["prior_live_submit_must_be_false"] is True
    assert duplicate["do_not_retry_without_reconciliation"] is True
    assert duplicate["prior_live_submit_found"] is False
    assert duplicate["dedupe_allows_submit"] is True
    assert OFFICIAL in duplicate["latest_idempotency_key"]


def test_no_env_config_lane_mutation_and_no_secrets_in_output(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r256(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_operator_real_submit_runbook(log_dir=log_dir, now=NOW)

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    _assert_runbook_safety(payload)
    _assert_no_secret_values(payload)


def _fixture_r256(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, Path]:
    log_dir, risk_path, lane_path, external = _fixture_r254(tmp_path, monkeypatch)
    r254 = build_tiny_live_submit_gate_preview(
        log_dir=log_dir,
        record_submit_gate_preview=True,
        confirm_tiny_live_submit_gate_preview=CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
        now=NOW,
    )
    assert r254["submit_gate_preview_recorded"] is True
    r255 = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        dry_run_actual_submit_gate=True,
        record_actual_submit_gate_preview=True,
        confirm_tiny_live_actual_submit_gate_preview=DRY_PREVIEW_CONFIRMATION_PHRASE,
        now=NOW + timedelta(minutes=5),
    )
    assert r255["actual_submit_executed"] is False
    assert r255["actual_submit_gate_matrix"]["blocked_by"] == [
        "signed_request_timestamp_stale",
        "official_lane_not_tiny_live",
        "live_execution_not_enabled",
    ]
    return log_dir, risk_path, lane_path, external


def _assert_runbook_safety(payload: Mapping[str, object]) -> None:
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
        "secrets_read",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["operator_runbook_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
