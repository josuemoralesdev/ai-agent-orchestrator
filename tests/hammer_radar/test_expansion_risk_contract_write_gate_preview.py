from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview import (
    EVENT_TYPE,
    FUTURE_CONFIRMATION_PHRASE_PREVIEW,
    LEDGER_FILENAME,
    PRIMARY_DRY_RUN_EXPANSION,
    REQUIRED_BASELINE,
    SECONDARY_WATCH_ONLY,
    WRITE_GATE_PREVIEW_BLOCKED_OPERATOR_REVIEW_REQUIRED,
    WRITE_GATE_PREVIEW_READY,
    build_expansion_risk_contract_write_gate_preview,
)
from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
    PRIMARY_DRY_RUN_EXPANSION_LANES,
)

NOW = datetime(2026, 6, 24, 16, 0, tzinfo=UTC)
BASELINE = "BTCUSDT|44m|long|ladder_close_50_618"


def test_module_runs_and_writes_preview_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")

    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write=True,
        now=NOW,
    )

    ledger = log_dir / LEDGER_FILENAME
    assert ledger.exists()
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event_type"] == EVENT_TYPE
    assert payload["event_type"] == EVENT_TYPE
    assert payload["proposed_contract_count"] == 8
    assert payload["write_gate_preview_only"] is True


def test_proposed_contracts_include_baseline_and_primary_lanes(tmp_path: Path) -> None:
    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json"),
        write=False,
        now=NOW,
    )
    by_role = {}
    for row in payload["proposed_contract_rows"]:
        by_role.setdefault(row["lane_role"], []).append(row["official_lane_key"])

    assert by_role[REQUIRED_BASELINE] == [BASELINE]
    assert by_role[PRIMARY_DRY_RUN_EXPANSION] == list(PRIMARY_DRY_RUN_EXPANSION_LANES)
    assert len(by_role[SECONDARY_WATCH_ONLY]) == 4


def test_no_config_or_arming_mutation_occurs(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json")
    arming_path = _write_arming_state(tmp_path / "autonomous_arming_state.json")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_arming = arming_path.read_text(encoding="utf-8")

    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=True,
        now=NOW,
    )

    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert arming_path.read_text(encoding="utf-8") == before_arming
    assert payload["risk_contract_config_mutated"] is False
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["config_written"] is False


def test_no_live_safety_flag_is_enabled(tmp_path: Path) -> None:
    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json"),
        write=False,
        now=NOW,
    )

    for key in (
        "live_execution_enabled",
        "allow_live_orders",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "submit_allowed",
        "final_command_available",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "leverage_change_called",
        "margin_change_called",
        "secrets_shown",
        "risk_contract_config_mutated",
        "global_live_flags_changed",
        "config_written",
        "env_written",
        "env_mutated",
    ):
        assert payload[key] is False
    assert payload["global_kill_switch"] is True
    assert payload["real_order_forbidden"] is True
    assert payload["paper_live_separation_intact"] is True
    assert payload["write_gate_preview_only"] is True


def test_future_confirmation_phrase_is_preview_only_not_executable(tmp_path: Path) -> None:
    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json"),
        write=False,
        now=NOW,
    )

    assert payload["future_confirmation_phrase_preview"] == FUTURE_CONFIRMATION_PHRASE_PREVIEW
    assert payload["future_confirmation_phrase_active"] is False
    assert payload["future_confirmation_phrase_executable"] is False
    assert "confirm" not in build_expansion_risk_contract_write_gate_preview.__code__.co_varnames


def test_max_loss_is_safely_derived_from_funding_config(tmp_path: Path) -> None:
    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json"),
        write=False,
        now=NOW,
    )

    assert payload["max_loss_derivation"]["derived"] is True
    assert payload["max_loss_derivation"]["max_loss_usdt"] == 4.44
    assert payload["max_loss_derivation"]["source"] == "funding_config.max_loss_usdt"
    for row in payload["proposed_contract_rows"]:
        assert row["proposed_contract"]["max_loss_usdt"] == 4.44
        assert row["write_gate_status"] == WRITE_GATE_PREVIEW_READY


def test_max_loss_blocks_operator_review_when_not_safely_derivable(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", max_loss=None)

    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=False,
        now=NOW,
    )

    assert payload["max_loss_derivation"]["derived"] is False
    assert payload["recommended_r309_path"] == "R309 Max Loss Derivation Review"
    for row in payload["proposed_contract_rows"]:
        assert row["proposed_contract"]["max_loss_usdt"] is None
        assert row["operator_review_required"] is True
        assert row["write_gate_status"] == WRITE_GATE_PREVIEW_BLOCKED_OPERATOR_REVIEW_REQUIRED
        assert "risk_contract_max_loss_requires_operator_review" in row["blocked_by"]


def test_existing_keys_are_not_modified_or_deleted_in_preview(tmp_path: Path) -> None:
    existing = "BTCUSDT|8m|short|ladder_close_50_618"
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", existing_lanes=[existing])
    before = risk_path.read_text(encoding="utf-8")

    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=False,
        now=NOW,
    )
    diff = payload["diff_preview"]

    assert existing in diff["would_not_modify_existing_keys"]
    assert existing in diff["would_not_delete_keys"]
    assert BASELINE in diff["would_add_lane_keys"]
    assert diff["existing_contract_count"] == 1
    assert diff["proposed_new_contract_count"] == 8
    assert risk_path.read_text(encoding="utf-8") == before


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "expansion-risk-contract-write-gate-preview",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["config_written"] is False
    assert payload["future_confirmation_phrase_executable"] is False


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r308_expansion_risk_contract_write_gate_preview.sh"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R308 EXPANSION RISK CONTRACT WRITE-GATE PREVIEW" in result.stdout
    assert "CURRENT CONFIG PATH" in result.stdout
    assert "PROPOSED CONTRACT COUNT" in result.stdout
    assert "BASELINE PROPOSED CONTRACT STATUS" in result.stdout
    assert "PRIMARY EXPANSION PROPOSED CONTRACT STATUSES" in result.stdout
    assert "SECONDARY WATCH-ONLY STATUSES" in result.stdout
    assert "MISSING OPERATOR REVIEW FIELDS" in result.stdout
    assert "FUTURE CONFIRMATION PHRASE PREVIEW" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "RECOMMENDED R309 PATH" in result.stdout


def test_no_secrets_or_binance_endpoints_called(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_expansion_risk_contract_write_gate_preview(
            log_dir=tmp_path / "logs",
            risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json"),
            write=False,
            now=NOW,
        )

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["secrets_shown"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False


def test_r307_r306_compatibility_remains_intact(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview import (
        build_eligible_lane_expansion_dry_run_preview,
    )
    from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
        build_expansion_risk_contract_preview_repair,
    )
    from tests.hammer_radar.test_eligible_lane_expansion_dry_run_preview import (
        FINAL_GATE_PACKET,
        FRESH_PACKET,
        TIMER_PACKET,
        _seed_strategy_status,
    )

    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    r307 = build_expansion_risk_contract_preview_repair(log_dir=log_dir, write=False, now=NOW)
    r306 = build_eligible_lane_expansion_dry_run_preview(
        log_dir=log_dir,
        write=False,
        now=NOW,
        timer_health_packet=TIMER_PACKET,
        final_gate_packet=FINAL_GATE_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
    )

    assert r307["event_type"] == "R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR"
    assert r306["event_type"] == "R306_ELIGIBLE_LANE_EXPANSION_DRY_RUN_PREVIEW"
    assert r307["config_written"] is False
    assert r306["risk_contract_config_mutated"] is False


def _write_risk_config(
    path: Path,
    *,
    max_loss: float | None = 4.44,
    existing_lanes: list[str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    funding_config = {
        "funding_config_present": True,
        "funding_check_mode": "LOCAL_CONFIG_ONLY_NO_NETWORK",
        "max_margin_usdt": 44.0,
    }
    if max_loss is not None:
        funding_config["max_loss_usdt"] = max_loss
    payload = {
        "funding_config": funding_config,
        "risk_contracts": [_contract(lane) for lane in existing_lanes or []],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_arming_state(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "armed_lane_key": BASELINE,
                "allowed_lane_keys": [BASELINE],
                "auto_execute_mode": "dry_run_only",
                "live_execution_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _contract(lane_key: str) -> dict[str, object]:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "official_lane_key": lane_key,
        "contract_version": "tiny_live_percentage_risk_contract_v2",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
        "max_position_notional_usdt": 80,
        "max_notional_usdt": 80,
        "leverage": 10,
        "margin_budget_usdt": 8,
        "max_margin_usdt": 8,
        "max_loss_usdt": 4.44,
        "margin_mode": "isolated",
        "protective_orders_required": True,
        "protective_stop_required": True,
        "take_profit_required": True,
        "live_execution_enabled": False,
        "live_authorized": False,
    }
