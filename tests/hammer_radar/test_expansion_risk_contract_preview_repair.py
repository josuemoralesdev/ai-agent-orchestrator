from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
    CURRENT_FIRST_TINY_LIVE_BASELINE,
    EVENT_TYPE,
    LEDGER_FILENAME,
    PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN,
    PRIMARY_DRY_RUN_EXPANSION_CANDIDATE,
    PRIMARY_DRY_RUN_EXPANSION_LANES,
    SECONDARY_WATCH_ONLY_CANDIDATE,
    build_expansion_risk_contract_lane_preview,
    build_expansion_risk_contract_preview_repair,
)

NOW = datetime(2026, 6, 24, 15, 0, tzinfo=UTC)
BASELINE = "BTCUSDT|44m|long|ladder_close_50_618"


def test_resolver_finds_existing_exact_contract_in_representative_config(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", lanes=[BASELINE])

    payload = build_expansion_risk_contract_lane_preview(
        lane_key=BASELINE,
        lane_role=CURRENT_FIRST_TINY_LIVE_BASELINE,
        risk_contract_config_path=risk_path,
    )

    assert payload["exact_contract_found"] is True
    assert payload["risk_contract_valid"] is True
    assert payload["matched_contract_key"] == BASELINE
    assert payload["safe_preview_template_status"] == "NOT_NEEDED_CONTRACT_FOUND"
    assert payload["safe_preview_template_if_missing"] == {}


def test_resolver_reports_missing_contract_with_preview_template_and_no_write(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", lanes=[BASELINE])
    before = risk_path.read_text(encoding="utf-8")
    missing_lane = PRIMARY_DRY_RUN_EXPANSION_LANES[0]

    payload = build_expansion_risk_contract_lane_preview(
        lane_key=missing_lane,
        lane_role=PRIMARY_DRY_RUN_EXPANSION_CANDIDATE,
        risk_contract_config_path=risk_path,
    )

    assert payload["exact_contract_found"] is False
    assert payload["risk_contract_valid"] is False
    assert payload["lookup_failure_reason"] == "no_contract_key_matched_normalized_lane_key"
    assert payload["safe_preview_template_status"] == PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN
    assert payload["safe_preview_template_if_missing"]["leverage"] == 10
    assert payload["safe_preview_template_if_missing"]["max_position_notional_usdt"] == 80
    assert payload["safe_preview_template_if_missing"]["margin_budget_usdt"] == 8
    assert "risk_contract_max_loss_requires_operator_review" in payload["blocked_by"]
    assert risk_path.read_text(encoding="utf-8") == before


def test_preview_inspects_baseline_primary_and_secondary_lanes(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", lanes=[BASELINE])
    payload = build_expansion_risk_contract_preview_repair(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=False,
        now=NOW,
    )
    by_role = {}
    for row in payload["lane_packets"]:
        by_role.setdefault(row["lane_role"], []).append(row["lane_key"])

    assert BASELINE in by_role[CURRENT_FIRST_TINY_LIVE_BASELINE]
    assert by_role[PRIMARY_DRY_RUN_EXPANSION_CANDIDATE] == list(PRIMARY_DRY_RUN_EXPANSION_LANES)
    assert len(by_role[SECONDARY_WATCH_ONLY_CANDIDATE]) == 4


def test_no_safety_flag_is_enabled_and_config_is_not_mutated(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "tiny_live_risk_contracts.json", lanes=[BASELINE])
    before = risk_path.read_text(encoding="utf-8")

    payload = build_expansion_risk_contract_preview_repair(
        log_dir=tmp_path / "logs",
        risk_contract_config_path=risk_path,
        write=True,
        now=NOW,
    )

    assert (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert risk_path.read_text(encoding="utf-8") == before
    assert payload["live_execution_enabled"] is False
    assert payload["allow_live_orders"] is False
    assert payload["global_kill_switch"] is True
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["risk_contract_config_mutated"] is False
    assert payload["config_written"] is False
    assert payload["secrets_shown"] is False


def test_r306_uses_repaired_resolver_after_r309_contract_apply(tmp_path: Path) -> None:
    from tests.hammer_radar.test_eligible_lane_expansion_dry_run_preview import (
        FINAL_GATE_PACKET,
        FRESH_PACKET,
        TIMER_PACKET,
        _seed_strategy_status,
    )
    from src.app.hammer_radar.operator.eligible_lane_expansion_dry_run_preview import (
        build_eligible_lane_expansion_dry_run_preview,
    )

    log_dir = tmp_path / "logs"
    _seed_strategy_status(log_dir)
    payload = build_eligible_lane_expansion_dry_run_preview(
        log_dir=log_dir,
        write=False,
        now=NOW,
        timer_health_packet=TIMER_PACKET,
        final_gate_packet=FINAL_GATE_PACKET,
        fresh_trigger_packet=FRESH_PACKET,
    )
    by_lane = {row["lane_key"]: row for row in payload["lane_packets"]}
    preview = by_lane[BASELINE]["exact_risk_contract_preview"]

    assert "lookup_attempts" in preview
    assert "safe_preview_template_status" in preview
    assert preview["exact_contract_found"] is True
    assert preview["risk_contract_valid"] is True
    assert preview["safe_preview_template_status"] == "NOT_NEEDED_CONTRACT_FOUND"


def test_inspect_route_works(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": "."}
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "expansion-risk-contract-preview-repair",
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


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")}
    result = subprocess.run(
        ["bash", "scripts/hammer_print_r307_expansion_risk_contract_preview_repair.sh"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "R307 EXPANSION RISK CONTRACT PREVIEW REPAIR" in result.stdout
    assert "BASELINE LANE CONTRACT STATUS" in result.stdout
    assert "PRIMARY DRY-RUN CANDIDATE CONTRACT STATUS" in result.stdout
    assert "SECONDARY WATCH-ONLY CONTRACT STATUS" in result.stdout
    assert "MISSING PREVIEW TEMPLATES SUMMARY" in result.stdout
    assert "R306 RECOMMENDED NEXT OPERATOR MOVE AFTER REPAIR" in result.stdout
    assert "SAFETY FLAGS" in result.stdout
    assert "RECOMMENDED R308 PATH" in result.stdout


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
        payload = build_expansion_risk_contract_preview_repair(
            log_dir=tmp_path / "logs",
            risk_contract_config_path=_write_risk_config(tmp_path / "tiny_live_risk_contracts.json", lanes=[]),
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


def _write_risk_config(path: Path, *, lanes: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"funding_config": {"funding_config_present": True}, "risk_contracts": [_contract(lane) for lane in lanes]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        "margin_mode": "ISOLATED_REQUIRED",
        "protective_stop_required": True,
        "take_profit_required": True,
        "live_execution_enabled": False,
        "live_authorized": False,
    }
