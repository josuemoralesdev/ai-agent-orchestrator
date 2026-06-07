from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.strategy_evidence_registry import (
    CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    STRATEGY_EVIDENCE_REGISTRY_RECORDED,
    STRATEGY_EVIDENCE_REGISTRY_REJECTED,
    build_strategy_evidence_registry,
    get_safety_manifest,
    load_strategy_evidence_registry_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_strategy_evidence_registry(log_dir=log_dir, now=NOW)

    assert payload["record_registry_requested"] is False
    assert payload["registry_recorded"] is False
    assert payload["registry_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"

    payload = build_strategy_evidence_registry(
        log_dir=log_dir,
        record_registry=True,
        confirm_strategy_evidence_registry="wrong",
        now=NOW,
    )

    assert payload["status"] == STRATEGY_EVIDENCE_REGISTRY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["registry_recorded"] is False
    assert load_strategy_evidence_registry_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_registry_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    before_env = dict(os.environ)

    payload = build_strategy_evidence_registry(
        log_dir=log_dir,
        record_registry=True,
        confirm_strategy_evidence_registry=CONFIRM_STRATEGY_EVIDENCE_REGISTRY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_strategy_evidence_registry_records(log_dir=log_dir, limit=0)

    assert payload["status"] == STRATEGY_EVIDENCE_REGISTRY_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["registry_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "STRATEGY_EVIDENCE_REGISTRY"
    assert before_env == dict(os.environ)


def test_manifest_includes_all_current_timeframes() -> None:
    payload = build_strategy_evidence_registry(now=NOW)

    assert payload["registry_manifest"]["timeframes"] == [
        "4m",
        "8m",
        "13m",
        "22m",
        "44m",
        "55m",
        "88m",
        "222m",
        "444m",
        "666m",
        "888m",
        "4H",
        "13H",
        "13D",
    ]


def test_manifest_includes_known_entry_modes() -> None:
    payload = build_strategy_evidence_registry(now=NOW)
    entry_modes = {row["entry_mode"]: row for row in payload["registry_manifest"]["entry_modes"]}

    for entry_mode in ("ladder_close_50_618", "ladder_382_50_618", "ladder_22_44_22", "market_close", "fib_618", "fib_650"):
        assert entry_mode in entry_modes
        assert entry_modes[entry_mode]["blocked_placeholder"] is False
    assert entry_modes["unknown"]["blocked_placeholder"] is True
    assert entry_modes["entry_unknown"]["blocked_placeholder"] is True


def test_manifest_includes_normal_signal_origins() -> None:
    payload = build_strategy_evidence_registry(now=NOW)
    manifest = payload["registry_manifest"]["signal_origins"]

    for origin in (
        "hammer_wick_reversal",
        "three_black_crows",
        "bearish_engulfing",
        "bullish_engulfing",
        "three_white_soldiers",
        "exhaustion_wick",
    ):
        assert origin in manifest["primary_normal"]
        assert manifest["origins"][origin]["live_authorized"] is False
        assert manifest["origins"][origin]["promotion_allowed"] is False


def test_manifest_includes_betrayal_candidates_222m_88m_55m() -> None:
    payload = build_strategy_evidence_registry(now=NOW)
    candidates = payload["registry_manifest"]["betrayal_candidates"]

    assert candidates["222m_aggregate"]["timeframe"] == "222m"
    assert candidates["88m_aggregate"]["timeframe"] == "88m"
    assert candidates["55m_aggregate_if_available"]["timeframe"] == "55m"
    for candidate in candidates.values():
        assert candidate["candidate_type"] == "aggregate"
        assert candidate["true_inverse_validation_required"] is True
        assert candidate["paper_only"] is True
        assert candidate["live_authorized"] is False
        assert candidate["promotion_allowed"] is False
        assert "source_identity" in candidate["required_before_promotion"]
        assert "Miro Fish support" in candidate["required_before_promotion"]


def test_manifest_includes_anchor_types_and_periods() -> None:
    payload = build_strategy_evidence_registry(now=NOW)
    anchors = payload["registry_manifest"]["anchors"]

    assert anchors["anchor_types"] == ["SMA200", "WMA200", "custom_wma"]
    assert anchors["anchor_periods"] == [13, 21, 34, 55, 89, 144, 200, 233, 377, 610, 888]
    assert anchors["live_authorized"] is False
    assert anchors["position_permission_created"] is False


def test_betrayal_v2_source_requirements_include_direction_identity_entry_mode() -> None:
    payload = build_strategy_evidence_registry(now=NOW)
    fields = payload["registry_manifest"]["source_identity_requirements"]["betrayal_source_emitter_v2"]

    for field in ("original_direction", "inverse_direction", "source_identity", "entry_mode"):
        assert field in fields


def test_all_families_default_live_and_order_false() -> None:
    safety_manifest = get_safety_manifest()

    for family, safety in safety_manifest.items():
        assert safety["paper_only"] is True, family
        assert safety["live_authorized"] is False, family
        assert safety["promotion_allowed"] is False, family
        assert safety["config_write_allowed"] is False, family
        assert safety["order_allowed"] is False, family
        assert safety["binance_network_allowed"] is False, family


def test_no_config_mutation_no_destructive_ledger_rewrite(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = tmp_path / "configs" / "lane_controls.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_strategy_evidence_registry(log_dir=log_dir, now=NOW)

    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["lane_config_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["ledger_rewritten"] is False
    assert payload["safety"]["destructive_write"] is False


def test_no_binance_network_order_live_transfer_or_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_strategy_evidence_registry(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "strategy-evidence-registry",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert "registry_manifest" in payload
    assert "strategy-evidence-registry" in help_result.stdout
